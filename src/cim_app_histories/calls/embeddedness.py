"""
Tracker embeddedness per app, per era.

How deeply is each tracker SDK wired into an app, and how does that
change across the app's releases? Answered with direct counts read from
the ``*.network.jsonl`` files a ``network`` run has already written -- no
APK is opened again.

Releases are grouped into ERAS by version name (all 3.* together, or all
3.103.* together), because single releases are noisy: obfuscated method
names change from one build to the next.

Why counts and not a centrality score: the tracker call graph runs one
way (app -> tracker -> network), and eigenvector centrality is all zeros
on a graph without cycles. Its scores are also scaled per graph, so they
cannot be compared between eras. Counts can.

"App" here means everything shipped in the APK outside the tracker
packages: the app's own classes AND its bundled libraries (androidx,
kotlin, Google common). The two cannot be told apart reliably once an
app is obfuscated, so ``app_callers`` and ``apk_code_called`` cover both.

Pure functions over parsed records, plus one CSV writer.
"""

import csv
import json
import re
from pathlib import Path

ERA_LEVELS = ("major", "minor", "release")

# Measured for one tracker in one release. Each is averaged over the
# releases of an era in which the tracker is present.
METRICS = (
    "app_callers",          # distinct non-tracker methods calling the tracker
    "call_sites",           # how many times they call it
    "entry_points",         # distinct tracker methods they call: API surface used
    "tracker_nodes",        # distinct tracker methods in the graph
    "apk_code_called",      # distinct non-tracker methods shipped in the APK
                            #   that the tracker calls: its dependence on the
                            #   rest of the app (callbacks and shared libraries)
    "network_apis",         # distinct network API classes the tracker reaches
    "network_call_sites",   # how many times it calls them
    "other_trackers",       # distinct other trackers it calls
)

CSV_COLUMNS = (
    ["pkg", "era", "tracker", "category", "level",
     "releases", "releases_present", "presence",
     "first_version", "last_version", "first_version_code",
     "last_version_code"]
    + list(METRICS)
    + ["app_methods_scanned", "app_caller_share"]
)


def era_of(version, level="major"):
    """Era label for a version name.

    ``3.103.0-6392`` is ``3.*`` at major level, ``3.103.*`` at minor
    level and itself at release level. Version names with no number in
    them fall into ``unknown``.
    """
    if level not in ERA_LEVELS:
        raise ValueError(f"era level must be one of {ERA_LEVELS}")
    version = (version or "").strip()
    if level == "release":
        return version or "unknown"
    parts = re.findall(r"\d+", version)
    if not parts:
        return "unknown"
    if level == "major" or len(parts) == 1:
        return f"{parts[0]}.*"
    return f"{parts[0]}.{parts[1]}.*"


def _era_sort_key(era):
    nums = [int(n) for n in re.findall(r"\d+", era)]
    return (0, nums, era) if nums else (1, [], era)


def release_metrics(record):
    """Embeddedness of every tracker in ONE release.

    :param record: one parsed ``*.network.jsonl`` record
    :returns: ``{signature: {"category": ..., <METRICS>...}}``
    """
    graph = record.get("graph") or {}
    kind, tracker, cls = {}, {}, {}
    out = {}

    def entry(sig, category=""):
        return out.setdefault(sig, {
            "category": category,
            "_app_callers": set(), "call_sites": 0, "_entry_points": set(),
            "_nodes": set(), "_callbacks": set(), "_network_apis": set(),
            "network_call_sites": 0, "_other_trackers": set()})

    for n in graph.get("nodes", []):
        nid = n["id"]
        kind[nid] = n.get("kind")
        cls[nid] = n.get("class", nid)
        sig = n.get("tracker")
        if sig:
            tracker[nid] = sig
            entry(sig, n.get("category", ""))["_nodes"].add(nid)

    for l in graph.get("links", []):
        src, dst = l["source"], l["target"]
        weight = l.get("weight", 1)
        src_sig, dst_sig = tracker.get(src), tracker.get(dst)

        if dst_sig and not src_sig:                 # app -> tracker
            e = entry(dst_sig)
            e["_app_callers"].add(src)
            e["_entry_points"].add(dst)
            e["call_sites"] += weight
        if src_sig:
            e = entry(src_sig)
            if dst_sig and dst_sig != src_sig:      # tracker -> other tracker
                e["_other_trackers"].add(dst_sig)
            elif kind.get(dst) == "network_api":    # tracker -> network
                e["_network_apis"].add(cls.get(dst, dst))
                e["network_call_sites"] += weight
            elif kind.get(dst) == "app":            # tracker -> rest of the APK
                e["_callbacks"].add(dst)

    for e in out.values():
        e["app_callers"] = len(e.pop("_app_callers"))
        e["entry_points"] = len(e.pop("_entry_points"))
        e["tracker_nodes"] = len(e.pop("_nodes"))
        e["apk_code_called"] = len(e.pop("_callbacks"))
        e["network_apis"] = len(e.pop("_network_apis"))
        e["other_trackers"] = len(e.pop("_other_trackers"))
    return out


def iter_network_records(paths):
    """Yield parsed records from ``*.network.jsonl`` files, skipping
    blank lines, error records and anything without a graph."""
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("graph"):
                    yield rec


def embeddedness_table(records, era_level="major"):
    """One row per (app, era, tracker).

    Within an era each metric is the MEAN over the releases in which the
    tracker is present; ``presence`` says in what share of the era's
    releases that is. Keeping the two apart stops "present in half the
    releases" being mistaken for "half as embedded".

    A union across the era would be wrong for these counts: a method
    renamed by the obfuscator between two builds would be counted twice.

    :param records: iterable of parsed ``*.network.jsonl`` records
    :param era_level: ``"major"``, ``"minor"`` or ``"release"``
    :returns: list of row dicts keyed by :data:`CSV_COLUMNS`, sorted by
        app, era, then tracker
    """
    # (pkg, era) -> {release key: (version, code, level, methods, metrics)}
    eras = {}
    for rec in records:
        pkg = rec.get("pkg") or "unknown"
        version = rec.get("version") or ""
        code = rec.get("version_code")
        code = code if isinstance(code, int) else None
        summary = rec.get("summary") or {}
        releases = eras.setdefault((pkg, era_of(version, era_level)), {})
        # the same release scanned twice (two copies of one APK) counts once
        releases.setdefault((code, version), (
            version, code, summary.get("level", ""),
            summary.get("methods_scanned"), release_metrics(rec)))

    rows = []
    for (pkg, era), releases in eras.items():
        ordered = sorted(releases.values(),
                         key=lambda r: (r[1] is None, r[1] or 0, r[0]))
        levels = sorted({r[2] for r in ordered if r[2]})
        signatures = sorted({sig for r in ordered for sig in r[4]})
        for sig in signatures:
            present = [r for r in ordered if sig in r[4]]
            n = len(present)
            row = {
                "pkg": pkg, "era": era, "tracker": sig,
                "category": present[0][4][sig].get("category", ""),
                "level": "+".join(levels),
                "releases": len(ordered),
                "releases_present": n,
                "presence": round(n / len(ordered), 3),
                "first_version": present[0][0],
                "last_version": present[-1][0],
                "first_version_code": present[0][1],
                "last_version_code": present[-1][1],
            }
            for metric in METRICS:
                row[metric] = round(
                    sum(r[4][sig][metric] for r in present) / n, 2)
            scanned = [r[3] for r in present if r[3]]
            row["app_methods_scanned"] = (
                round(sum(scanned) / len(scanned)) if scanned else None)
            # Share of the app's code that talks to this tracker. Only
            # meaningful at method level, where callers are methods too.
            row["app_caller_share"] = (
                round(row["app_callers"] / row["app_methods_scanned"], 6)
                if scanned and levels == ["method"] else None)
            rows.append(row)

    rows.sort(key=lambda r: (r["pkg"], _era_sort_key(r["era"]), r["tracker"]))
    return rows


def write_embeddedness_csv(rows, path):
    """Write the table as CSV, atomically. Returns the row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if row.get(k) is None else row[k])
                                 for k in CSV_COLUMNS})
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return len(rows)
