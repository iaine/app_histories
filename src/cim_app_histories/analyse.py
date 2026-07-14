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


def collect_all_files(apk_path):
    """Open an APK and gather its files, merging sibling split APKs when
    the base contains no native libraries.

    :returns: (apk, files, info) where info records native_libs count,
        any splits_merged, and incomplete_base_apk (True when no native
        libs were found and no splits could be located).
    """
    from androguard.core.apk import APK
    apk = APK(str(apk_path))
    files = collect_apk_files(apk)
    info = {"native_libs": sum(1 for n, _ in files if n.endswith(".so")),
            "splits_merged": []}

    if info["native_libs"] == 0:
        for sib in gather_split_apks(apk_path):
            try:
                sapk = APK(str(sib))
            except Exception:
                continue
            sfiles = collect_apk_files(sapk)
            if any(n.endswith(".so") for n, _ in sfiles):
                files.extend(sfiles)
                info["splits_merged"].append(sib.name)
        info["native_libs"] = sum(1 for n, _ in files if n.endswith(".so"))

    info["incomplete_base_apk"] = (
        info["native_libs"] == 0 and not info["splits_merged"])
    return apk, files, info


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


# ---------------------------------------------------------------------------
# Public one-call wrappers (notebook / script entry points)
# ---------------------------------------------------------------------------
def analyse_flows(apk_path, dx=None, config=None, profiler=None):
    """Build the input -> module -> endpoint flow graph for one APK file.

    Does the full ingestion the CLI does: split-APK merging and DEX URL
    extraction (literal + runtime-assembled). Returns the graph dict with
    a ``sankey`` key and source provenance merged into the summary; adds
    a ``warning`` key when the input looks like an incomplete bundle base.

    :param apk_path: path to a .apk file
    :param dx: optional androguard Analysis to enable method tracing
    :param config: {"inputs": [...]} to restrict inputs
    :param profiler: optional StageProfiler for per-stage timing/memory
    """
    apk, files, info = collect_all_files(apk_path)
    dex_urls = extract_dex_urls(apk)
    graph = build_flow_graph(files, permissions=apk.get_permissions(),
                             dx=dx, config=config, dex_urls=dex_urls,
                             profiler=profiler)
    graph["summary"] = {**graph["summary"], **info}
    graph["sankey"] = to_sankey(graph)
    graph["app"] = {"pkg": apk.get_package(),
                     "version": apk.get_androidversion_name()}
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
