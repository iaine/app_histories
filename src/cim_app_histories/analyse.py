"""
APK ingestion and high-level analysis entry points.

This module bridges an APK file on disk to the pure, parallel-safe
workflow functions (build_flow_graph, trace_listening). The workflow
functions take pre-extracted ``(name, bytes)`` files plus ``dex_urls``
so they stay free of androguard and remain testable; this module does
the androguard I/O once and hands them what they need.

Use the wrappers for a notebook / script:

    from cim_app_histories.analyse import analyse_flows, analyse_listening
    graph = analyse_flows("MyApp.apk")
    listening = analyse_listening("MyApp.apk")

The CLI uses the same helpers, so the notebook path and the batch path
behave identically (split-APK merging, DEX URL extraction including
runtime-assembled URLs, and the incomplete-base warning all apply).
"""

from pathlib import Path

from .calls.multimodal_pipeline import build_flow_graph, to_sankey, looks_like_model
from .calls.listening import trace_listening
from .bundle import is_bundle, open_bundle


def collect_apk_files(apk):
    """Native libs + model assets from one opened APK, using the shared
    model-detection heuristic so .bin/ggml/ncnn models are included."""
    out = []
    for f in apk.get_files():
        if f.endswith(".so") or looks_like_model(f):
            out.append((f, apk.get_file(f)))
    return out


def gather_split_apks(apk_path):
    """Sibling split APKs of a base App Bundle download.

    Apps installed from Play or pulled from a device arrive as a base
    apk plus split_config.<abi>.apk files holding the native libraries;
    analysing the base alone sees zero .so files. Returns siblings that
    look like splits of the same package in the same directory.
    """
    base = Path(apk_path)
    sibs = []
    for cand in sorted(base.parent.glob("*.apk")):
        if cand == base:
            continue
        n = cand.name.lower()
        if ("split" in n or "config." in n or n.startswith(base.stem.lower())
                or cand.stem.startswith(base.stem)):
            sibs.append(cand)
    return sibs


def _merge_member_apks(member_paths):
    """Open each chosen bundle member and merge their files, base first.

    Only splits that add *new* native libraries contribute them, matching
    the loose-split rule, so a language split cannot inflate the file set
    and the same ``.so`` is never merged twice.
    """
    from androguard.core.apk import APK
    base_apk, files, seen, merged = None, [], set(), []
    for i, p in enumerate(member_paths):
        try:
            apk = APK(str(p))
        except Exception:
            continue
        if base_apk is None:
            base_apk = apk
            for n, d in collect_apk_files(apk):
                if n not in seen:
                    files.append((n, d))
                    seen.add(n)
        else:
            new = [(n, d) for n, d in collect_apk_files(apk) if n not in seen]
            if new:
                files.extend(new)
                seen.update(n for n, _ in new)
                merged.append(Path(p).name)
    return base_apk, files, merged


def collect_all_files(apk_path):
    """Open an APK (or bundle) and gather its files, merging splits.

    Two shapes of split App Bundle are handled by the same rule -- merge
    anything that adds native libraries:

    * **loose splits**: a base ``.apk`` with sibling ``config.<abi>.apk``
      files in the same directory (a Play or device pull).
    * **packaged bundles**: ``.xapk`` / ``.apks`` / ``.apkm``, where the
      base and splits are zipped together. Live Transcribe's base holds
      zero native libraries while all seven sit in ``config.arm64_v8a.apk``,
      so without unpacking the bundle the app looks empty.

    The base may itself carry some libraries (Otter's base has graphics
    ``.so`` while its audio libraries sit in a split), so merging is not
    conditional on the base being empty.

    :returns: (apk, files, info) where info records native_libs count,
        any splits_merged, incomplete_base_apk, and -- for a packaged
        bundle -- a ``bundle`` provenance block.
    """
    from androguard.core.apk import APK

    if is_bundle(apk_path):
        import tempfile
        # The temp dir lives for this one app's analysis and is removed
        # after; per-task, so the HPC batch model is unaffected.
        with tempfile.TemporaryDirectory() as td:
            member_paths, meta = open_bundle(apk_path, td)
            apk, files, merged = _merge_member_apks(member_paths)
            if apk is None:
                raise ValueError(f"no readable APK inside bundle {apk_path}")
            info = {
                "native_libs": sum(1 for n, _ in files if n.endswith(".so")),
                "splits_merged": merged,
                "bundle": meta,
            }
            info["incomplete_base_apk"] = (
                info["native_libs"] == 0 and not merged)
            return apk, files, info

    apk = APK(str(apk_path))
    files = collect_apk_files(apk)
    seen = {n for n, _ in files}
    info = {"native_libs": sum(1 for n, _ in files if n.endswith(".so")),
            "splits_merged": []}

    for sib in gather_split_apks(apk_path):
        try:
            sapk = APK(str(sib))
        except Exception:
            continue
        sfiles = collect_apk_files(sapk)
        # only merge a split that adds native libraries not already present,
        # so a language/density split doesn't inflate the file set and the
        # same lib isn't merged twice
        new_so = [(n, d) for n, d in sfiles
                  if n.endswith(".so") and n not in seen]
        if new_so:
            files.extend(new_so)
            seen.update(n for n, _ in new_so)
            info["splits_merged"].append(sib.name)
    info["native_libs"] = sum(1 for n, _ in files if n.endswith(".so"))

    info["incomplete_base_apk"] = (
        info["native_libs"] == 0 and not info["splits_merged"])
    return apk, files, info


def extract_dex_egress(apk):
    """Capture-to-egress evidence from the DEX, unioned across dex files.

    Returns ``{input_id: {"capture": [...], "output": [...],
    "proximity": "method"|"class"|None}}``.

    **Co-occurrence, not dataflow**: proximity records whether capture and
    network APIs are called in the same method (strongest), the same class
    (weaker), or merely both present (None). It never asserts the recorded
    audio is what is transmitted.
    """
    from .dex.dex import analyseDEX
    rank = {None: 0, "class": 1, "method": 2}
    merged = {}
    try:
        for dex in apk.get_all_dex():
            try:
                for k, v in analyseDEX(dex).trace_capture_egress().items():
                    slot = merged.setdefault(
                        k, {"capture": set(), "output": set(),
                            "proximity": None})
                    slot["capture"].update(v.get("capture", []))
                    slot["output"].update(v.get("output", []))
                    if rank[v.get("proximity")] > rank[slot["proximity"]]:
                        slot["proximity"] = v["proximity"]
            except Exception:
                continue
    except Exception:
        pass
    return {k: {"capture": sorted(v["capture"]),
                "output": sorted(v["output"]),
                "proximity": v["proximity"]} for k, v in merged.items()}


def extract_dex_urls(apk):
    """All http(s) URLs in the app's DEX: whole-string literals plus URLs
    assembled at runtime from fragments (StringBuilder, Uri.Builder,
    Retrofit/OkHttp). Chat/streaming backends are usually Java/Kotlin
    constants, not native-library strings, and are frequently built from
    fragments, so both styles are gathered via analyseDEX.all_urls()."""
    from .dex.dex import analyseDEX
    urls = set()
    try:
        for dex in apk.get_all_dex():
            try:
                urls.update(analyseDEX(dex).all_urls())
            except Exception:
                continue
    except Exception:
        pass
    return sorted(urls)


def extract_dex_inputs(apk):
    """Framework-level capture inputs evidenced by API calls in the app's
    DEX -- e.g. ``{"microphone": ["AudioRecord"]}``. Mirrors
    extract_dex_urls: some apps (Otter) capture audio through the Android
    framework (AudioRecord) in Java/Kotlin and ship no audio native
    library, so the microphone input is invisible to native-.so scanning
    but present in the DEX. Unions the per-dex evidence across every
    classes*.dex."""
    from .dex.dex import analyseDEX
    merged = {}
    try:
        for dex in apk.get_all_dex():
            try:
                for k, v in analyseDEX(dex).audio_inputs().items():
                    merged.setdefault(k, set()).update(v)
            except Exception:
                continue
    except Exception:
        pass
    return {k: sorted(v) for k, v in merged.items()}


# ---------------------------------------------------------------------------
# Public one-call wrappers (notebook / script entry points)
# ---------------------------------------------------------------------------
def analyse_flows(apk_path, dx=None, config=None, profiler=None,
                  dex_trace=True):
    """Build the input -> module -> endpoint flow graph for one APK file.

    Does the full ingestion the CLI does: split-APK merging and DEX URL
    extraction (literal + runtime-assembled). Returns the graph dict with
    a ``sankey`` key and source provenance merged into the summary; adds
    a ``warning`` key when the input looks like an incomplete bundle base.

    :param apk_path: path to a .apk file
    :param dx: optional androguard Analysis to enable method tracing
    :param config: {"inputs": [...]} to restrict inputs
    :param profiler: optional StageProfiler for per-stage timing/memory
    :param dex_trace: run the capture->egress DEX trace (default True).
        Costs a second pass over every method (~40s on a large app), so
        corpus runs that only need inputs can pass False.
    """
    apk, files, info = collect_all_files(apk_path)
    dex_urls = extract_dex_urls(apk)
    dex_inputs = extract_dex_inputs(apk)
    # The egress trace is a second full pass over every method's invokes,
    # ~40s on a large app (Otter). Corpus runs that only need inputs can
    # switch it off; it is on by default because capture->network is the
    # machine-listening finding the flows graph otherwise cannot state.
    dex_egress = extract_dex_egress(apk) if dex_trace else {}
    graph = build_flow_graph(files, permissions=apk.get_permissions(),
                             dx=dx, config=config, dex_urls=dex_urls,
                             dex_inputs=dex_inputs, dex_egress=dex_egress,
                             profiler=profiler)
    graph["summary"] = {**graph["summary"], **info}
    pkg = apk.get_package()
    version = apk.get_androidversion_name()
    graph["app"] = {"pkg": pkg, "version": version}
    # Gephi (and any node-table consumer) reads per-NODE attributes, not a
    # top-level object. Stamp pkg/version onto every node so the Data
    # Laboratory columns populate, and also expose them as flat top-level
    # keys so a converter reading record["pkg"] finds them regardless of
    # whether it expects the flat or the nested ("app") shape.
    graph["pkg"] = pkg
    graph["version"] = version
    for node in graph["nodes"]:
        node.setdefault("pkg", pkg)
        node.setdefault("version", version)
    graph["sankey"] = to_sankey(graph)
    if info["incomplete_base_apk"]:
        graph["warning"] = ("no native libraries found; likely a split App "
                            "Bundle base APK. Provide the universal APK or "
                            "split_config.*.apk files for complete analysis.")
    return graph


def analyse_listening(apk_path):
    """Trace audio inputs -> chain -> models/endpoints for one APK file.

    Same ingestion as analyse_flows (split merging, DEX URLs including
    runtime-assembled audio backends). Returns the listening result dict;
    adds a ``warning`` key when the input looks like an incomplete base.

    :param apk_path: path to a .apk file
    """
    apk, files, info = collect_all_files(apk_path)
    dex_urls = extract_dex_urls(apk)
    result = trace_listening(files, permissions=apk.get_permissions(),
                             dex_urls=dex_urls)
    result["summary"] = {**result.get("summary", {}), **info}
    result["app"] = {"pkg": apk.get_package(),
                     "version": apk.get_androidversion_name()}
    if info["incomplete_base_apk"]:
        result["warning"] = ("no native libraries found; likely a split App "
                             "Bundle base APK. Provide the universal APK or "
                             "split_config.*.apk files for complete analysis.")
    return result
