
"""
Multimodal AI Pipeline Detector
================================

This module provides a configurable pipeline to detect and connect AI processing
flows across modalities: audio, video, image, NLP, and their combinations.

Features:
- Detects modality-specific processing (.so, models, etc.)
- Infers input, method, output
- Detects vendor (ByteDance, Tencent, Google, etc.)
- Connects flows across modalities:
    audio -> NLP
    image -> NLP
    video -> image
    video -> image -> NLP
- Outputs compact JSON structure
- Generates Sankey-compatible graph edges

Usage Example:
--------------

files = [(filename, binary_data), ...]
config = {"modes": ["audio", "video", "image", "nlp"]}

pipeline = build_multimodal_pipeline(files, config)
edges = to_sankey(pipeline["flows"])
"""

import re


from androguard.core.analysis.analysis import Analysis
from androguard.core.dex import DEX
from androguard.core.apk import APK

from loguru import logger
logger.remove()  # removes all loguru handlers
logger.add(lambda msg: None, level="CRITICAL")

# =========================
# STRING EXTRACTION
# =========================
PRINTABLE_RE = re.compile(rb"[ -~]{3,}")

def extract_strings(data):
    return [m.decode("ascii", errors="ignore") for m in PRINTABLE_RE.findall(data)]

# =========================
# VENDOR DETECTION
# =========================
def detect_vendor(file, data):
    name = file.lower()
    strings = extract_strings(data)
    text = " ".join(strings).lower()

    if any(k in name for k in ["byte", "tt"]):
        return "bytedance"
    if any(k in name for k in ["tenny", "tnn"]):
        return "tencent"
    if "mediapipe" in name or "google" in text:
        return "google"
    if "huawei" in text:
        return "huawei"
    return "unknown"

# =========================
# AUDIO
# =========================
def is_audio_processing_so(name, strings):
    n = name.lower()
    t = " ".join(strings).lower()
    return any(k in n for k in ["audio", "sound", "voice", "speech"]) or            sum(1 for k in ["audio", "voice", "speech", "pcm"] if k in t) >= 3


def detect_audio_input(strings, file):
    t = " ".join(strings).lower()
    if "microphone" in t:
        return "spoken_audio", "microphone"
    if any(ext in file for ext in [".wav", ".mp3"]):
        return "audio_file", "file"
    return "audio", "unknown"


def detect_audio_method(strings):
    t = " ".join(strings).lower()
    if "speech" in t:
        return "speech_to_text"
    if "classify" in t:
        return "audio_classification"
    return "audio_processing"


def detect_audio_output(strings):
    t = " ".join(strings).lower()
    if "text" in t:
        return "text", "string"
    return "features", "vector"

# =========================
# VIDEO
# =========================
def is_video_processing_so(name, strings):
    n = name.lower()
    return any(k in n for k in ["video", "frame", "demux"]) 


def detect_video_input(strings, file):
    t = " ".join(strings).lower()
    if "camera" in t:
        return "video_stream", "camera"
    return "video", "unknown"


def detect_video_method(strings):
    t = " ".join(strings).lower()
    if "face" in t:
        return "face_detection"
    return "video_processing"


def detect_video_output(strings):
    return "frames", "image"

# =========================
# IMAGE
# =========================
def is_image_processing(name, strings):
    n = name.lower()
    return any(k in n for k in ["image", "vision", "face", "photo"])


def detect_image_input(strings, file):
    return "image", "file"


def detect_image_method(strings):
    t = " ".join(strings).lower()
    if "object" in t:
        return "object_detection"
    return "image_processing"


def detect_image_output(strings):
    return "detections", "coordinates"

# =========================
# NLP
# =========================
def is_nlp_processing(name, strings):
    n = name.lower()
    return any(k in n for k in ["nlp", "text", "bert"])


def detect_nlp_input(strings):
    return "text", "string"


def detect_nlp_method(strings):
    t = " ".join(strings).lower()
    if "sentiment" in t:
        return "sentiment_analysis"
    return "nlp_processing"


def detect_nlp_output(strings):
    return "classification", "label"

# =========================
# FLOW BUILDING
# =========================
def resolve_vendor(a, b):
    if a.get("vendor") != "unknown":
        return a["vendor"]
    return b.get("vendor", "unknown")


def generate_flows(files, config):
    flows = []

    for f, data in files:
        strings = extract_strings(data)
        vendor = detect_vendor(f, data)

        if "audio" in config["modes"] and is_audio_processing_so(f, strings):
            inp, im = detect_audio_input(strings, f)
            method = detect_audio_method(strings)
            out, om = detect_audio_output(strings)
            flows.append({"mode": "audio", "vendor": vendor, "input": inp, "input_method": im, "processor": f, "method": method, "output": out, "output_method": om})

        if "video" in config["modes"] and is_video_processing_so(f, strings):
            inp, im = detect_video_input(strings, f)
            method = detect_video_method(strings)
            out, om = detect_video_output(strings)
            flows.append({"mode": "video", "vendor": vendor, "input": inp, "input_method": im, "processor": f, "method": method, "output": out, "output_method": om})

        if "image" in config["modes"] and is_image_processing(f, strings):
            inp, im = detect_image_input(strings, f)
            method = detect_image_method(strings)
            out, om = detect_image_output(strings)
            flows.append({"mode": "image", "vendor": vendor, "input": inp, "input_method": im, "processor": f, "method": method, "output": out, "output_method": om})

        if "nlp" in config["modes"] and is_nlp_processing(f, strings):
            inp, im = detect_nlp_input(strings)
            method = detect_nlp_method(strings)
            out, om = detect_nlp_output(strings)
            flows.append({"mode": "nlp", "vendor": vendor, "input": inp, "input_method": im, "processor": f, "method": method, "output": out, "output_method": om})

    return {"flows": flows}

# =========================
# CONNECTIONS
# =========================

def connect_audio_nlp(flows):
    combined = []
    for a in flows:
        if a["mode"] != "audio": continue
        for n in flows:
            if n["mode"] != "nlp": continue
            if a["output"] == "text":
                combined.append({
                    "mode": "audio_nlp",
                    "vendor": resolve_vendor(a, n),
                    "input": a["input"],
                    "chain": [a["method"], n["method"]],
                    "output": n["output"]
                })
    return combined


def connect_image_nlp(flows):
    combined = []
    for i in flows:
        if i["mode"] != "image": continue
        for n in flows:
            if n["mode"] != "nlp": continue
            combined.append({
                "mode": "image_nlp",
                "vendor": resolve_vendor(i, n),
                "input": i["input"],
                "chain": [i["method"], n["method"]],
                "output": n["output"]
            })
    return combined


def connect_video_image_nlp(flows):
    combined = []
    for v in flows:
        if v["mode"] != "video": continue
        for i in flows:
            if i["mode"] != "image": continue
            for n in flows:
                if n["mode"] != "nlp": continue
                combined.append({
                    "mode": "video_image_nlp",
                    "vendor": resolve_vendor(v, n),
                    "input": v["input"],
                    "chain": [v["method"], i["method"], n["method"]],
                    "output": n["output"]
                })
    return combined

# =========================
# MAIN PIPELINE
# =========================

def build_multimodal_pipeline(files, config):
    base = generate_flows(files, config)
    flows = base["flows"]

    flows.extend(connect_audio_nlp(flows))
    flows.extend(connect_image_nlp(flows))
    flows.extend(connect_video_image_nlp(flows))

    return {"flows": flows}

# =========================
# SANKEY EXPORT
# =========================

def to_sankey(flows):
    edges = []
    for f in flows:
        ch = f.get("chain")
        if not ch: continue

        edges.append({"source": f["input"], "target": ch[0], "value": 1})
        for i in range(len(ch)-1):
            edges.append({"source": ch[i], "target": ch[i+1], "value": 1})
        edges.append({"source": ch[-1], "target": f["output"], "value": 1})

    return edges

if __name__ == "__main__":
    apkname = "/Users/iain/Documents/projects/machinelistening/tiktok/TikTok - Videos, Shop & LIVE_43.7.3_APKPure.apk"
    apk = APK(apkname)

    files = []
    for f in apk.get_files():
        if f.endswith(".so") or f.endswith((".so", ".tflite", ".onnx", ".pb", ".dat", ".model")):
            data = apk.get_file(f)
            files.append((f, data))
    
    config = {"modes": ["audio", "video", "image", "nlp"]}

    pipeline = build_multimodal_pipeline(files, config)
    edges = to_sankey(pipeline["flows"])
    print(pipeline)