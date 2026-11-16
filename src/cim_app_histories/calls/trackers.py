"""
Contains the tracker classes for the calls module.
"""
from build.lib.cim_app_histories import dex
from build.lib.cim_app_histories.general.perf import NullProfiler
from cim_app_histories.analysis.analysis import Analyse
import json
import os
import re

from cim_app_histories.calls.curl_classifier import CurlClassifier
from cim_app_histories.calls.multimodal import _ENDPOINT_NOISE, _BARE_EXAMPLE, is_noise_endpoint


def trace_trackers(inputdir, outputdir):
    """
    Track the given call.

    Args:
        call: The call object to be tracked.
    """
    trackers = tracker_list(outputdir)
    analysis = Analyse()
    analysis.callgraph(trackers)

def tracker_list(outputdir):
    """
    List all available trackers. Read trackers in the given output directory 
    and return a list of tracker names.

    Args:
        outputdir: The directory where the metadatalist is stored.
    Returns:
        A list of tracker names with types for the application. 
    """

    if os.path.exists(outputdir):
        return list(set([get_metadata(outputdir, f) for f in os.listdir(outputdir) \
                         if f.endswith("metadata.jsonl") and os.path.isfile(os.path.join(outputdir, f))]))

def get_metadata(outputdir, tracker_name):
    """
    Get the metadata for a specific tracker.

    Args:
        outputdir: The directory where the metadatalist is stored.
        tracker_name: The name of the tracker for which to retrieve metadata.
    Returns:
        A list of dictionaries containing the metadata for the specified tracker.
    """

    metadata_file = os.path.join(outputdir, tracker_name)
    read_json = json.load(open(metadata_file, "r"))
    return [ {'signature': f['signature'], 'category': f['category']} for f in read_json.get("trackers", [])]

# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_tracker_graph(files, trackers, dx=None, config=None,
                     profiler=None, dex_urls=None, dex_inputs=None,
                     dex_egress=None):
    """Build the input -> module -> onward graph for one app.

    :param files: iterable of (name, bytes) -- native libs and model assets
    :param permissions: app manifest permissions (corroboration evidence)
    :param dx: optional androguard Analysis; enables method tracing
    :param config: {"inputs": [...]} to restrict which inputs to look for
    :param profiler: optional StageProfiler; per-stage timing/memory is
        recorded under it (NullProfiler default: zero overhead)
    :param dex_urls: optional list of URL strings extracted from the app's
        DEX (Java/Kotlin) code. Most chat/streaming backends live here, not
        in native libraries, so without this an LLM client or music app
        shows no endpoints. Attributed to an "app_code" node.
    :param dex_inputs: optional {input_id: [api names]} of framework-level
        capture inputs found in the DEX (e.g. {"microphone": ["AudioRecord"]}).
        Apps that record via the Android framework in Java/Kotlin (Otter:
        AudioRecord, no audio native library) are invisible to native-.so
        input scanning; this makes the microphone input appear. Attributed
        to the "app_code" node, with evidence kind "dex_api".
    :returns: {"nodes": [...], "links": [...], "summary": {...}}
    """
    profiler = profiler or NullProfiler()

    with profiler.stage("trace_input_apis"):
        traced = trace_input_apis(dx) if dx is not None else {}

    curl = CurlClassifier()

    nodes, links = {}, []
    chain = []          # staged, per-modality processing entries

    def add_node(node_id, **attrs):
        nodes.setdefault(node_id, {"id": node_id, **attrs})

    for tracker in trackers:
        add_node(tracker['signature'], kind="tracker", category=tracker['category'])
        tracked_class = "L" + tracker['signature'].replace(".", "/") + ";"
        for m in dex.find_methods(classname=tracked_class):
            orig_method = m.get_method()

        for _, callee, _ in m.get_xref_to():

            if callee not in nodes:
                add_node(callee, kind="method", external=isinstance(callee, ExternalMethod))

            if not any(link for link in links if link["source"] == orig_method and link["target"] == callee):
                links.append({"source": orig_method, "target": callee})

    # ---- app (dex) -> endpoint links: chat/streaming backends live in
    # Java/Kotlin, not native libs. Filter library boilerplate so the
    # app's own backend is not buried under DoH/analytics/CDN constants.
    with profiler.stage("dex_endpoints"):
        if dex_urls:
            app_node = "app_code"
            seen_ep = set()
            for url in dex_urls:
                dom = curl.get_domain_safe(url)
                if not dom:
                    continue
                tmpl = curl.generate_template(url)
                endpoint = dom + tmpl
                if endpoint in seen_ep or is_noise_endpoint(url) \
                        or is_noise_endpoint(endpoint):
                    continue
                seen_ep.add(endpoint)
                cats = curl.classify_url(url)
                add_node(app_node, kind="module", category="app_code")
                add_node(endpoint, kind="endpoint", categories=cats)
                links.append({"source": app_node, "target": endpoint,
                              "kind": "sends_to", "score": 1,
                              "evidence": {"source_layer": "dex",
                                           "url_categories": cats}})
                chain.append({"modality": "network", "stage": "output",
                              "module": app_node, "endpoint": endpoint,
                              "source_layer": "dex", "categories": cats})

    with profiler.stage("dex_inputs"):
        if dex_inputs:
            app_node = "app_code"
            for input_id, apis in dex_inputs.items():
                if input_id not in wanted:
                    continue
                score = 2                       # a framework call is solid
                ev = {"dex_api": sorted(apis), "source_layer": "dex"}
                perm_hit = sorted(
                    {p for p in INPUT_SIGNATURES.get(input_id, {})
                        .get("permissions", []) if p in (permissions or [])})
                if perm_hit:
                    score += 1
                    ev["permissions"] = perm_hit
                modality = INPUT_MODALITY.get(input_id, "unknown")
                add_node(input_id, kind="input", modality=modality)
                add_node(app_node, kind="module", category="app_code")
                links.append({"source": input_id, "target": app_node,
                              "modality": modality, "kind": "feeds",
                              "score": score, "evidence": ev})
                chain.append({"modality": modality, "stage": "capture",
                              "module": app_node, "input": input_id,
                              "source_layer": "dex",
                              "operations": sorted(apis)})
    with profiler.stage("dex_egress"):
        for input_id, ev in (dex_egress or {}).items():
            if input_id not in wanted or not ev.get("output"):
                continue
            proximity = ev.get("proximity")
            modality = INPUT_MODALITY.get(input_id, "unknown")
            add_node("app_code", kind="module", category="app_code")
            chain.append({
                "modality": modality, "stage": "output",
                "module": "app_code", "input": input_id,
                "source_layer": "dex",
                "operations": sorted(ev["output"]),
                "evidence": {"proximity": proximity,
                             "relation": "co-occurrence",
                             "capture": sorted(ev.get("capture", []))},
            })



    summary = {
        "inputs": sorted({l["source"] for l in links if l["kind"] == "feeds"}),
        "modules": len(modules),
        "models": len(models),
        "endpoints": sorted({l["target"] for l in links
                             if l["kind"] == "sends_to"})[:20],
        "endpoints_from_dex": sum(1 for l in links if l["kind"] == "sends_to"
                                  and l.get("evidence", {}).get("source_layer") == "dex"),
        "models_total": len(models),
        "models_linked": sum(1 for n in nodes.values()
                             if n.get("kind") == "model" and n.get("linked")),
        "method_traced": bool(traced),
        "modalities": sorted({e["modality"] for e in chain
                              if e.get("modality") not in (None, "unknown")}),
        "stages_present": sorted({e["stage"] for e in chain},
                                 key=STAGE_ORDER.index),
    }
    chain.sort(key=lambda e: (e.get("modality") or "", STAGE_ORDER.index(e["stage"])))
    return {"nodes": list(nodes.values()), "links": links,
            "chain": chain,
            "parameter_transitions": parameter_transitions(chain),
            "summary": summary}
