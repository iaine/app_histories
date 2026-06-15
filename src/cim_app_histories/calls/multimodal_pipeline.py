"""
AI flow-graph extraction: trace inputs -> modules -> onward processes.

Builds a lightweight, JSON-serialisable graph of how data may flow
through an app's AI components:

    input (microphone, camera, bluetooth_midi, text, network_stream,
           file, sensor, screen)
      -> module (a native library, classified via ClassifySO; or a
                 model asset, classified via ClassifyModel)
      -> onward (a network endpoint via ClassifyURL -- e.g. a model
                 whose host library talks to a streaming/upload API --
                 or a produced output such as text or labels)

Design rules (these are the contract, not aspirations):

* EVIDENCE-GATED LINKS. A link exists only with concrete, co-located
  evidence: the input's keywords/API names found in *that module's own
  strings*, optionally corroborated by a manifest permission. Nothing
  is connected by cross product. (The previous implementation joined
  every image flow to every NLP flow unconditionally, fabricating
  pipelines; that behaviour is deliberately gone.)
* INTERNATIONALISED. Keyword tables carry English and Chinese terms,
  and matching runs over a tolerant UTF-8 decode of the binary as well
  as ASCII strings -- CJK strings are invisible to ASCII-only
  extraction. Tables are data; add languages by extending them.
* CHAINS STAY INTERNAL. Optional dex method tracing strengthens link
  evidence, but the traced chains themselves are summarised (api,
  depth, count) and never emitted in the final graph.
* PURE AND PARALLEL-SAFE. No I/O, no printing, no logger mutation, no
  androguard import at module level. ``build_flow_graph`` takes
  (name, bytes) pairs plus optional permissions and returns data,
  so it drops straight into the CLI's per-task HPC batch model.

Output shape (per app):

    {"nodes": [{"id", "kind", ...}],
     "links": [{"source", "target", "kind", "score", "evidence"}],
     "summary": {...}}
"""

import re
from collections import Counter

from ..classify.classify_so import ClassifySO
from ..classify.classify_url import ClassifyURL
from ..classify.classify_model import ClassifyModel
from ..general.perf import NullProfiler

# ---------------------------------------------------------------------------
# Input signature tables (data, not code: extend keywords/languages here)
# ---------------------------------------------------------------------------
# keywords: matched in the module's own strings (ASCII, lowercased) and in
#   a tolerant UTF-8 decode (for CJK). Distinct keywords score 1 each.
# apis: Android API class names; found in module strings they score 2
#   (strong: the module references the input API directly).
# permissions: app-level manifest permissions. Corroboration only (+1):
#   a permission alone never creates a link, because permissions are not
#   evidence about a *particular* module.
INPUT_SIGNATURES = {
    "microphone": {
        "keywords": ["microphone", "audiorecord", "mediarecorder", "pcm_in",
                     "voice input", "record_audio",
                     "\u9ea6\u514b\u98ce",       # 麦克风 microphone
                     "\u5f55\u97f3",             # 录音 (audio) recording
                     "\u8bed\u97f3\u8f93\u5165"],# 语音输入 voice input
        "apis": ["android/media/audiorecord", "android/media/mediarecorder"],
        "permissions": ["android.permission.RECORD_AUDIO"],
    },
    "camera": {
        "keywords": ["camera2", "camera", "preview_frame", "imagereader",
                     "\u6444\u50cf\u5934",       # 摄像头 camera
                     "\u76f8\u673a",             # 相机 camera
                     "\u62cd\u6444"],            # 拍摄 shoot/capture
        "apis": ["android/hardware/camera", "android/media/imagereader"],
        "permissions": ["android.permission.CAMERA"],
    },
    "bluetooth_midi": {
        "keywords": ["midimanager", "mididevice", "bluetooth", "ble_midi",
                     "midi",
                     "\u84dd\u7259"],            # 蓝牙 bluetooth
        "apis": ["android/media/midi/midimanager",
                 "android/bluetooth/bluetoothadapter"],
        "permissions": ["android.permission.BLUETOOTH",
                        "android.permission.BLUETOOTH_CONNECT"],
    },
    "text_input": {
        "keywords": ["inputmethod", "ime_", "keyboard", "edittext",
                     "\u8f93\u5165\u6cd5",       # 输入法 input method
                     "\u952e\u76d8"],            # 键盘 keyboard
        "apis": ["android/view/inputmethod/inputmethodmanager"],
        "permissions": [],
    },
    "network_stream": {
        "keywords": ["exoplayer", "hls", "rtmp", "m3u8", "dash_", "webrtc",
                     "streaming", "spotify", "deezer",
                     "\u76f4\u64ad",             # 直播 live stream
                     "\u6d41\u5a92\u4f53"],      # 流媒体 streaming media
        "apis": ["android/media/mediaplayer"],
        "permissions": ["android.permission.INTERNET"],
    },
    "file": {
        "keywords": ["fopen", "content://", "/storage/", "documentfile",
                     "file_descriptor",
                     "\u6587\u4ef6"],            # 文件 file
        "apis": ["android/provider/documentscontract"],
        "permissions": ["android.permission.READ_EXTERNAL_STORAGE",
                        "android.permission.READ_MEDIA_AUDIO",
                        "android.permission.READ_MEDIA_IMAGES"],
    },
    "sensor": {
        "keywords": ["sensormanager", "accelerometer", "gyroscope",
                     "\u4f20\u611f\u5668"],      # 传感器 sensor
        "apis": ["android/hardware/sensormanager"],
        "permissions": ["android.permission.BODY_SENSORS",
                        "android.permission.ACTIVITY_RECOGNITION"],
    },
    "screen": {
        "keywords": ["mediaprojection", "screenshot", "screen_record",
                     "\u622a\u5c4f",             # 截屏 screenshot
                     "\u5f55\u5c4f"],            # 录屏 screen recording
        "apis": ["android/media/projection/mediaprojectionmanager"],
        "permissions": [],
    },
}

# Onward "produces" outputs, also i18n.
OUTPUT_SIGNATURES = {
    "text": ["speech_to_text", "transcrib", "asr_result", "ocr_result",
             "\u8bc6\u522b\u7ed3\u679c",        # 识别结果 recognition result
             "\u8f6c\u5199"],                    # 转写 transcription
    "labels": ["classif", "label", "category_id", "confidence",
               "\u5206\u7c7b"],                  # 分类 classification
    "translation": ["translat",
                    "\u7ffb\u8bd1"],             # 翻译 translation
    "synthesized_audio": ["text_to_speech", "tts_", "synthes",
                          "\u5408\u6210"],       # 合成 synthesis
    "embeddings": ["embedding", "feature_vector", "\u5411\u91cf"],  # 向量
}

MODEL_EXTENSIONS = (".tflite", ".lite", ".onnx", ".pt", ".ptl", ".pb",
                    ".mnn", ".param", ".nb", ".ms", ".om", ".bytenn",
                    ".model", ".dat", ".caffemodel", ".gguf", ".ggml",
                    ".rknn", ".ncnn", ".pdmodel", ".pdiparams", ".safetensors",
                    ".weights", ".ckpt", ".pkl", ".npz", ".spm", ".vocab")

# Name hints that make an ambiguous ".bin" / no-extension asset a model.
_MODEL_NAME_HINT = re.compile(
    r"(model|weight|\bnet\b|tflite|onnx|ggml|gguf|ncnn|mnn|paddle|"
    r"tensor|infer|embed|encoder|decoder|vocab|token|asr|tts|nlp|bert|"
    r"detect|classif|recogni|face|voice|speech)", re.I)


def looks_like_model(name):
    """True if a file is a model asset by extension, or an under-assets
    .bin/.dat/extension-less file whose name hints at a model. The old
    fixed-extension list missed .bin-packaged models (ggml/ncnn/llama)
    that are extremely common, leaving real models undetected."""
    low = name.lower()
    if low.endswith(MODEL_EXTENSIONS):
        return True
    if ("assets/" in low or "/ml/" in low or "model" in low):
        if low.endswith((".bin", ".data", ".pb.bin")) or "." not in name.rsplit("/", 1)[-1]:
            return bool(_MODEL_NAME_HINT.search(low))
    return False

MIN_LINK_SCORE = 2   # one generic keyword alone never creates a link


# ---------------------------------------------------------------------------
# Text views over a binary
# ---------------------------------------------------------------------------
def make_text_views(classify_so, data):
    """Return (ascii_text, i18n_text): lowered ASCII strings joined, and a
    tolerant UTF-8 decode for CJK keyword search. ClassifySO's extractor
    is ASCII+UTF-16LE only, so Chinese UTF-8 strings need this view."""
    strings = classify_so.extract_strings(data)
    ascii_text = " ".join(strings).lower()
    i18n_text = data.decode("utf-8", errors="ignore")
    return strings, ascii_text, i18n_text


def find_evidence(signature, ascii_text, i18n_text, permissions):
    """Score one input signature against one module's text views."""
    keywords = sorted({k for k in signature["keywords"]
                       if k in ascii_text or k in i18n_text})
    apis = sorted({a for a in signature.get("apis", []) if a in ascii_text})
    perms = sorted({p for p in signature.get("permissions", [])
                    if p in permissions})

    score = len(keywords) + 2 * len(apis)
    if score > 0 and perms:        # corroboration only
        score += 1

    return score, {"keywords": keywords, "apis": apis, "permissions": perms}


# ---------------------------------------------------------------------------
# Optional dex method tracing (chains stay internal)
# ---------------------------------------------------------------------------
def trace_input_apis(dx, max_depth=2):
    """Walk callers of known input APIs up to ``max_depth``. Returns
    {input_id: {"apis": {api: caller_package_prefixes}}}. The traversal
    chain is used here and then discarded -- only the api name, depth
    reached, and caller packages survive into link evidence."""
    traced = {}
    for input_id, sig in INPUT_SIGNATURES.items():
        for api in sig.get("apis", []):
            classname = "L" + api.replace(".", "/")
            try:
                methods = list(dx.find_methods(classname=classname + ".*"))
            except Exception:
                continue
            packages = set()
            frontier = methods
            depth = 0
            while frontier and depth < max_depth:
                nxt = []
                for m in frontier:
                    try:
                        for _, call, _ in m.get_xref_from():
                            cn = str(call.class_name)
                            packages.add("/".join(cn.strip("L;").split("/")[:3]))
                            nxt.append(call)
                    except Exception:
                        continue
                frontier = nxt
                depth += 1
            if packages:
                entry = traced.setdefault(input_id, {"apis": {}})
                entry["apis"][api] = {"depth": depth,
                                      "caller_packages": sorted(packages)[:8]}
    return traced


def trace_strengthens(traced, input_id, module_name, vendor):
    """A trace strengthens a link when a caller package shares a vendor or
    name token with the module (e.g. com/bytedance/speech callers and a
    bytedance speech library)."""
    info = traced.get(input_id)
    if not info:
        return None
    tokens = {t for t in re.split(r"[^a-z0-9]+", module_name.lower()) if len(t) > 3}
    if vendor and vendor != "unknown":
        tokens.add(vendor)
    for api, detail in info["apis"].items():
        for pkg in detail["caller_packages"]:
            if any(t in pkg for t in tokens):
                return {"api": api, "depth": detail["depth"]}
    return None


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_flow_graph(files, permissions=None, dx=None, config=None,
                     profiler=None):
    """Build the input -> module -> onward graph for one app.

    :param files: iterable of (name, bytes) -- native libs and model assets
    :param permissions: app manifest permissions (corroboration evidence)
    :param dx: optional androguard Analysis; enables method tracing
    :param config: {"inputs": [...]} to restrict which inputs to look for
    :param profiler: optional StageProfiler; per-stage timing/memory is
        recorded under it (NullProfiler default: zero overhead)
    :returns: {"nodes": [...], "links": [...], "summary": {...}}
    """
    profiler = profiler or NullProfiler()
    permissions = set(permissions or [])
    wanted = set((config or {}).get("inputs", INPUT_SIGNATURES))

    cso, curl, cmodel = ClassifySO(), ClassifyURL(), ClassifyModel()
    with profiler.stage("trace_input_apis"):
        traced = trace_input_apis(dx) if dx is not None else {}

    nodes, links = {}, []

    def add_node(node_id, **attrs):
        nodes.setdefault(node_id, {"id": node_id, **attrs})

    modules, models = [], []
    for name, data in files:
        if looks_like_model(name):
            models.append((name, data))
        elif name.endswith(".so"):
            modules.append((name, data))

    module_views = {}
    for name, data in modules:
        with profiler.stage("text_views"):
            strings, ascii_text, i18n_text = make_text_views(cso, data)
        with profiler.stage("classify_module"):
            category, _ = cso.classify_so_pre(name, data)
            vendor = cso.detect_vendor(name, strings)
        module_views[name] = (strings, ascii_text, i18n_text, vendor)
        add_node(name, kind="module", category=category, vendor=vendor)

        # ---- input -> module links (evidence-gated)
        with profiler.stage("input_links"):
            for input_id in wanted:
                score, ev = find_evidence(INPUT_SIGNATURES[input_id],
                                          ascii_text, i18n_text, permissions)
                if score <= 0:
                    continue
                trace = trace_strengthens(traced, input_id, name, vendor)
                if trace:
                    score += 2
                    ev["method_trace"] = trace  # api + depth only, no chain
                if score >= MIN_LINK_SCORE:
                    add_node(input_id, kind="input")
                    links.append({"source": input_id, "target": name,
                                  "kind": "feeds", "score": score,
                                  "evidence": ev})

        # ---- module -> endpoint links (onward: network)
        with profiler.stage("url_links"):
            url_infos = curl.find_urls_with_analysis(strings)
        for url_info in url_infos:
            endpoint = url_info["domain"] + url_info["template"]
            add_node(endpoint, kind="endpoint",
                     categories=url_info["categories"])
            links.append({"source": name, "target": endpoint,
                          "kind": "sends_to", "score": 1,
                          "evidence": {"url_categories": url_info["categories"]}})

        # ---- module -> output links (onward: produced data)
        for out_id, kws in OUTPUT_SIGNATURES.items():
            hits = sorted({k for k in kws
                           if k in ascii_text or k in i18n_text})
            if len(hits) >= 1 and (len(hits) >= 2 or category == "ml_runtime"):
                add_node(out_id, kind="output")
                links.append({"source": name, "target": out_id,
                              "kind": "produces", "score": len(hits),
                              "evidence": {"keywords": hits}})

    # ---- module -> model links: graduated co-location evidence.
    # Real apps rarely embed a model's exact stem in a library's strings:
    # filenames carry version/quantisation suffixes (ggml_model_q4 vs the
    # referenced ggml_model), models are loaded from Java, or referenced by
    # directory. So match in descending strength and record which rule
    # fired, instead of requiring the full stem verbatim (which silently
    # left almost every real model unlinked).
    with profiler.stage("model_links"):
        for mname, mdata in models:
            base = mname.rsplit("/", 1)[-1].lower()           # voice_v2.tflite
            stem = base.rsplit(".", 1)[0]                      # voice_v2
            # significant tokens from the stem (drop version/quant noise)
            tokens = [t for t in re.split(r"[^a-z0-9]+", stem)
                      if len(t) >= 4 and not re.fullmatch(r"v?\d+|q\d+|fp\d+|int\d+", t)]

            referenced_by = []          # list of (module, match_rule, score)
            for n, (_, a, i, _) in module_views.items():
                hay = a + " " + i
                if base in hay:
                    referenced_by.append((n, "filename", 3))
                elif len(stem) >= 4 and stem in hay:
                    referenced_by.append((n, "stem", 3))
                else:
                    hit = [t for t in tokens if t in hay]
                    if hit:
                        referenced_by.append((n, "token:" + ",".join(hit), 2))

            context = " ".join(module_views[r][1] for r, _, _ in referenced_by) \
                if referenced_by else " ".join(a for _, a, _, _ in module_views.values())
            info = cmodel.classify(mname, mdata, context_text=context)
            add_node(mname, kind="model", format=info["format"],
                     modality=info["modality"], vendor=info["vendor"],
                     linked=bool(referenced_by))
            for ref, rule, score in referenced_by:
                links.append({"source": ref, "target": mname,
                              "kind": "uses_model", "score": score,
                              "evidence": {"name_reference": rule}})

    summary = {
        "inputs": sorted({l["source"] for l in links if l["kind"] == "feeds"}),
        "modules": len(modules),
        "models": len(models),
        "endpoints": sorted({l["target"] for l in links
                             if l["kind"] == "sends_to"})[:20],
        "models_total": len(models),
        "models_linked": sum(1 for n in nodes.values()
                             if n.get("kind") == "model" and n.get("linked")),
        "method_traced": bool(traced),
    }
    return {"nodes": list(nodes.values()), "links": links, "summary": summary}


# ---------------------------------------------------------------------------
# Sankey export (duplicate edges merged; widths mean something)
# ---------------------------------------------------------------------------
def to_sankey(graph):
    counts = Counter((l["source"], l["target"]) for l in graph["links"])
    return [{"source": s, "target": t, "value": v}
            for (s, t), v in sorted(counts.items())]
