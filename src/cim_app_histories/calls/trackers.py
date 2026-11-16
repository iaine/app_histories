"""
Tracker network call graph.

For each app, record which code calls into third-party tracker SDKs and
what the tracker code calls in turn (network APIs, the Android framework,
other libraries):

    app code  ->  tracker SDK  ->  network API / framework / library

The tracker signatures come from the ``trackers`` field of the
``*.metadata.jsonl`` files a ``metadata`` run has already written, read
ONCE into a single shared table and applied to every APK.

Design rules:

* ONE PASS, NO XREF. Edges are read straight from the ``invoke``
  instructions of each method. androguard's ``Analysis.create_xref()``
  gives the same edges but took 132s and was then killed for memory on a
  real app (Otter); the invoke scan took 39s and about 0.9 GB there.
* PLAIN CONTAINERS WHILE BUILDING. Nodes and edges accumulate in dicts
  (cheap to grow, free de-duplication). networkx is only touched once, in
  ``write_graphml``, after every app has been merged.
* PURE AND PARALLEL-SAFE. No androguard import at module level, no
  printing. ``build_tracker_graph`` takes DEX-like objects and returns
  data, so it drops into the CLI's per-task batch model. Only
  ``tracker_list``, ``merge_network_records`` and ``write_graphml`` touch
  the disk.

An edge means "this method contains a call to that one". Interface
dispatch and reflection are not resolved, so the graph under-reports
rather than over-reports.
"""

import json
import re
from pathlib import Path

# "v1, Lokhttp3/OkHttpClient;->newCall(Lokhttp3/Request;)Lokhttp3/Call;"
_INVOKE_RE = re.compile(r"(L[^;\s]+;)->([^\s(]+)(\([^)]*\)\S*)")

NODE_KINDS = ("app", "tracker", "network_api", "external")


# ---------------------------------------------------------------------------
# Tracker table: read the metadata results once
# ---------------------------------------------------------------------------
def tracker_list(input_dir):
    """Union of the trackers named in every ``*.metadata.jsonl`` file
    under ``input_dir``.

    Read once per run and shared with every APK scan, so the metadata
    directory is not re-read per app.

    :param input_dir: directory holding the metadata results
    :returns: ``{signature: {"name": ..., "category": ...}}``, keyed by
        the dotted package signature (``com.appsflyer``)
    """
    base = Path(input_dir)
    if not base.is_dir():
        raise FileNotFoundError(f"metadata directory not found: {base}")

    trackers = {}
    for path in sorted(base.glob("*.metadata.jsonl")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue            # a truncated line must not stop a run
                for t in record.get("trackers") or []:
                    sig = (t.get("signature") or "").strip()
                    if sig:
                        trackers.setdefault(sig, {
                            "name": t.get("name", ""),
                            "category": t.get("category", ""),
                        })
    return dict(sorted(trackers.items()))


def _descriptor_prefixes(trackers):
    """Class-descriptor prefixes for each signature, longest first so
    that nested signatures (``com.google.android.gms.ads.identifier``
    inside ``com.google.android.gms.ads``) resolve to the most specific.

    Anchored like ``find_trackers``: ``com.split`` matches the package
    ``com/split/`` but not ``com/splitties/``."""
    out = []
    for sig in sorted(trackers, key=len, reverse=True):
        d = "L" + sig.replace(".", "/")
        out.append((d + "/", sig))      # a class in the package
        out.append((d + ";", sig))      # the signature is itself a class
        out.append((d + "$", sig))      # ... or one of its inner classes
    return out


# ---------------------------------------------------------------------------
# Graph construction (pure)
# ---------------------------------------------------------------------------
def build_tracker_graph(dexes, trackers, network_apis=(), level="method",
                        include_internal=False):
    """Build the tracker call graph for one app.

    :param dexes: iterable of androguard ``DEX``-like objects. Pass a
        generator so only one parsed DEX is alive at a time.
    :param trackers: ``{signature: {"name", "category"}}`` from
        :func:`tracker_list`
    :param network_apis: descriptor prefixes that mark a callee as a
        network API (``"Lokhttp3/"``, ``"Ljava/net/Socket"``)
    :param level: ``"method"`` for one node per method, ``"class"`` to
        collapse methods into their class (a much smaller graph)
    :param include_internal: keep calls that stay inside one tracker.
        Off by default: on a real app they were nearly half of all edges
        and say nothing about what the tracker touches.
    :returns: ``{"nodes": [...], "links": [...], "summary": {...}}``
    """
    if level not in ("method", "class"):
        raise ValueError("level must be 'method' or 'class'")

    prefixes = _descriptor_prefixes(trackers)
    network_apis = tuple(network_apis)
    sig_cache = {}

    def tracker_of(cls):
        """Signature owning this class descriptor, or None. Cached: the
        same classes recur across a million invokes."""
        try:
            return sig_cache[cls]
        except KeyError:
            sig = None
            for prefix, s in prefixes:
                if cls.startswith(prefix):
                    sig = s
                    break
            sig_cache[cls] = sig
            return sig

    nodes = {}          # id -> attrs
    edges = {}          # (source, target) -> [kind, call-site count]
    defined = set()     # every class this app ships code for
    methods_seen = invokes_seen = 0

    def node_id(cls, name, desc):
        return cls if level == "class" else f"{cls}->{name}{desc}"

    def add_node(nid, cls, name, sig, callee_ref):
        if nid in nodes:
            return
        if sig:
            kind = "tracker"
        elif network_apis and callee_ref and callee_ref.startswith(network_apis):
            kind = "network_api"
        else:
            kind = "external"           # settled after the scan, see below
        short = cls[1:-1].rsplit("/", 1)[-1]
        attrs = {"id": nid, "kind": kind,
                 "label": short if level == "class" else f"{short}.{name}",
                 "class": cls}
        if sig:
            attrs["tracker"] = sig
            attrs["category"] = trackers[sig].get("category", "")
        nodes[nid] = attrs

    for dex in dexes:
        try:
            methods = dex.get_encoded_methods()
        except AttributeError:          # test doubles
            methods = dex.get_methods()
        for method in methods:
            try:
                caller_cls = str(method.get_class_name())
                defined.add(caller_cls)
                code = method.get_code()
                if code is None:
                    continue
                caller_sig = tracker_of(caller_cls)
                methods_seen += 1
                caller_id = None        # built only if this method has an edge
                for ins in code.get_bc().get_instructions():
                    if not ins.get_name().startswith("invoke"):
                        continue
                    invokes_seen += 1
                    m = _INVOKE_RE.search(ins.get_output() or "")
                    if not m:
                        continue
                    callee_cls, callee_name, callee_desc = m.groups()
                    callee_sig = tracker_of(callee_cls)
                    if not caller_sig and not callee_sig:
                        continue        # nothing to do with a tracker
                    internal = caller_sig is not None and caller_sig == callee_sig
                    if internal and not include_internal:
                        continue

                    if caller_id is None:
                        caller_name = str(method.get_name())
                        caller_id = node_id(caller_cls, caller_name,
                                            str(method.get_descriptor()))
                        add_node(caller_id, caller_cls, caller_name, caller_sig,
                                 f"{caller_cls}->{caller_name}")
                    callee_id = node_id(callee_cls, callee_name, callee_desc)
                    if callee_id == caller_id:
                        continue        # class-level self loop
                    add_node(callee_id, callee_cls, callee_name, callee_sig,
                             f"{callee_cls}->{callee_name}")

                    if internal:
                        kind = "internal"
                    elif callee_sig and not caller_sig:
                        kind = "calls_tracker"
                    elif nodes[callee_id]["kind"] == "network_api":
                        kind = "network"
                    elif callee_sig:
                        kind = "tracker_to_tracker"
                    else:
                        kind = "tracker_calls"
                    edge = edges.get((caller_id, callee_id))
                    if edge is None:
                        edges[(caller_id, callee_id)] = [kind, 1]
                    else:
                        edge[1] += 1
            except Exception:
                continue                # one undecodable method is not fatal

    # "app" is code shipped in the APK outside every tracker (the app's
    # own classes and its bundled libraries); "external" is everything the
    # APK only refers to -- the Android framework and the JDK. This can
    # only be decided once every DEX has been seen, since a callee may be
    # defined in a later classes*.dex.
    for n in nodes.values():
        if n["kind"] == "external" and n["class"] in defined:
            n["kind"] = "app"

    links = [{"source": s, "target": t, "kind": k, "weight": w}
             for (s, t), (k, w) in edges.items()]
    found = sorted({n["tracker"] for n in nodes.values() if "tracker" in n})
    summary = {
        "level": level,
        "trackers_searched": len(trackers),
        "trackers_found": found,
        "nodes": len(nodes),
        "links": len(links),
        "node_kinds": _count(n["kind"] for n in nodes.values()),
        "link_kinds": _count(l["kind"] for l in links),
        "network_apis_reached": sorted(
            {n["class"] for n in nodes.values() if n["kind"] == "network_api"}),
        "methods_scanned": methods_seen,
        "invokes_scanned": invokes_seen,
    }
    return {"nodes": list(nodes.values()), "links": links, "summary": summary}


def _count(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# Corpus merge and GraphML (the only place networkx is used)
# ---------------------------------------------------------------------------
def merge_network_records(paths):
    """Fold per-app ``*.network.jsonl`` records into one node table and
    one edge table, still as plain dicts.

    App-code nodes are kept separate per app (``<pkg>::<id>``): two apps
    both having a class ``La/b;`` share nothing but an obfuscated name.
    Tracker, network-API and external nodes are shared by descriptor, so
    the same SDK in two apps is ONE node and the apps meet there. Shared
    nodes carry ``apps``, the number of apps they were seen in.

    :param paths: iterable of ``*.network.jsonl`` paths
    :returns: ``(nodes, edges, apps)`` -- ``{id: attrs}``,
        ``{(source, target): attrs}`` and the list of merged apps
    """
    nodes, edges, apps = {}, {}, []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                graph = rec.get("graph")
                if not graph:
                    continue
                pkg = rec.get("pkg") or Path(path).name
                version = rec.get("version") or ""
                apps.append({"pkg": pkg, "version": version})

                def gid(nid, kind, _pkg=pkg):
                    return f"{_pkg}::{nid}" if kind == "app" else nid

                kinds = {}
                for n in graph["nodes"]:
                    kinds[n["id"]] = n["kind"]
                    key = gid(n["id"], n["kind"])
                    cur = nodes.get(key)
                    if cur is None:
                        cur = nodes[key] = {
                            "kind": n["kind"], "label": n.get("label", ""),
                            "class": n.get("class", ""),
                            "tracker": n.get("tracker", ""),
                            "category": n.get("category", ""),
                            "pkg": pkg if n["kind"] == "app" else "",
                            "version": version if n["kind"] == "app" else "",
                            "apps": 0,
                        }
                    cur["apps"] += 1
                for l in graph["links"]:
                    key = (gid(l["source"], kinds.get(l["source"], "")),
                           gid(l["target"], kinds.get(l["target"], "")))
                    cur = edges.get(key)
                    if cur is None:
                        edges[key] = {"kind": l["kind"],
                                      "weight": l.get("weight", 1), "apps": 1}
                    else:
                        cur["weight"] += l.get("weight", 1)
                        cur["apps"] += 1
    return nodes, edges, apps


def write_graphml(nodes, edges, path):
    """Translate the finished node and edge tables into a networkx
    ``DiGraph`` and write it as GraphML. Called once, at the very end.

    GraphML attributes must be scalars, which the tables already are
    (strings and ints only).

    :returns: ``(node count, edge count)``
    """
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.items())
    graph.add_edges_from((s, t, attrs) for (s, t), attrs in edges.items())

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        nx.write_graphml(graph, tmp)
        tmp.replace(path)               # never leave a half-written graph
    finally:
        tmp.unlink(missing_ok=True)
    return graph.number_of_nodes(), graph.number_of_edges()
