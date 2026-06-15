"""
Listening workflow: trace audio inputs and their parameters through an
app's processing chain to an output (model, produced data, or endpoint).

Built for machine-listening studies: how does an app capture sound, what
does it do to the signal, what does a model receive, and what leaves the
device? The unit of analysis is the *parameter vocabulary* a binary's
strings reveal -- sample rates, channel layouts, frame/hop sizes, mel
bins, codecs, DSP operations -- organised into a canonical stage chain:

    capture -> dsp -> features -> inference -> output

and, where the same parameter appears with different values in
successive stages, a recorded *transition* (e.g. sample_rate 48000 at
capture but 16000 at features: the resample-for-ASR signature).

Honesty contract (same spirit as the flows workflow):

* Evidence-gated: a module enters the chain only with audio evidence in
  its OWN strings; sources attach only with co-located keyword/API
  evidence (permissions corroborate, never establish).
* Static limits stated: parameters are vocabulary observed in strings,
  not measured runtime values. A "16000" near "sample_rate" is strong
  evidence of a 16 kHz path; it is not a recording of one. Transitions
  are inferred from stage co-location and deserve sample auditing.
* Internationalised: keyword tables carry English and Chinese terms,
  matched over a tolerant UTF-8 decode as well as ASCII strings.
* Pure and parallel-safe: takes (name, bytes) pairs plus permissions,
  returns a dict; no I/O, no logging mutation, no androguard import at
  module level.
"""

import re
from collections import defaultdict

from ..classify.classify_so import ClassifySO
from ..classify.classify_url import ClassifyURL
from ..classify.classify_model import ClassifyModel
from .multimodal_pipeline import (
    INPUT_SIGNATURES, MODEL_EXTENSIONS, make_text_views, find_evidence,
    looks_like_model, is_noise_endpoint,
)

# Path/host hints that an endpoint is audio-related (upload of recordings,
# streaming, transcription, recommendation). Used only to TAG dex endpoints
# audio_related=True/False, not to drop them.
AUDIO_ENDPOINT_HINT = re.compile(
    r"(audio|voice|speech|asr|tts|transcri|stream|hls|rtmp|dash|"
    r"recommend|playlist|track|listen|sound|record|upload)", re.I)

# ---------------------------------------------------------------------------
# Audio sources: the inputs this workflow traces (subset of the flow
# tables, plus audio-specific extras)
# ---------------------------------------------------------------------------
AUDIO_SOURCES = {
    "microphone": INPUT_SIGNATURES["microphone"],
    "bluetooth_midi": INPUT_SIGNATURES["bluetooth_midi"],
    "network_stream": INPUT_SIGNATURES["network_stream"],
    "audio_file": {
        "keywords": [".wav", ".mp3", ".flac", ".ogg", ".m4a", "audio_file",
                     "\u97f3\u9891\u6587\u4ef6"],          # 音频文件
        "apis": ["android/media/mediaextractor"],
        "permissions": ["android.permission.READ_MEDIA_AUDIO"],
    },
}

# ---------------------------------------------------------------------------
# Stage vocabulary (data, not code: extend operations/languages here)
# ---------------------------------------------------------------------------
STAGE_ORDER = ["capture", "dsp", "features", "inference", "output"]

STAGE_OPERATIONS = {
    "capture": [
        "audiorecord", "opensl", "aaudio", "audio_capture", "pcm_in",
        "recorder", "\u5f55\u97f3",                        # 录音
    ],
    "dsp": [
        "resample", "src_", "downsample", "denoise", "noise_suppress",
        "ns_", "aec", "echo_cancel", "agc", "gain_control", "vad",
        "voice_activity", "beamform", "webrtc_apm", "loudness", "lufs",
        "\u964d\u566a",                                    # 降噪 denoise
        "\u56de\u58f0",                                    # 回声 echo
        "\u589e\u76ca",                                    # 增益 gain
    ],
    "features": [
        "fft", "stft", "spectrogram", "mel", "mfcc", "fbank", "filterbank",
        "log_mel", "cepstral", "pitch_", "f0_", "chroma",
        "\u9891\u8c31",                                    # 频谱 spectrum
        "\u7279\u5f81\u63d0\u53d6",                        # 特征提取
    ],
    "inference": [
        "interpreter", "inference", "tflite", "onnx", "predict",
        "asr", "speech_to_text", "recognize", "wakeword", "hotword",
        "keyword_spot", "speaker_id", "embedding", "classif",
        "\u8bc6\u522b",                                    # 识别 recognise
        "\u5524\u9192",                                    # 唤醒 wake
        "\u63a8\u7406",                                    # 推理 inference
    ],
    "output": [
        "transcript", "subtitle", "caption", "label", "upload", "post_",
        "send_audio", "playlist", "recommend", "next_track", "for_you",
        "\u8f6c\u5199",                                    # 转写 transcribe
        "\u63a8\u8350",                                    # 推荐 recommend
    ],
}

# Inference task labels, ordered by specificity
INFERENCE_TASKS = [
    ("speech_to_text", ["asr", "speech_to_text", "transcrib", "recognize",
                        "\u8bed\u97f3\u8bc6\u522b"]),       # 语音识别
    ("wake_word", ["wakeword", "hotword", "keyword_spot", "\u5524\u9192"]),
    ("speech_synthesis", ["text_to_speech", "tts_", "synthes",
                          "\u8bed\u97f3\u5408\u6210"]),      # 语音合成
    ("speaker_recognition", ["speaker_id", "speaker_verif", "voiceprint",
                             "\u58f0\u7eb9"]),               # 声纹
    ("music_analysis", ["music_", "beat_", "tempo", "genre", "recommend",
                        "playlist"]),
    ("audio_classification", ["audio_classif", "sound_event", "audioset"]),
    ("audio_embedding", ["embedding", "feature_vector"]),
]

# ---------------------------------------------------------------------------
# Parameter extraction
# ---------------------------------------------------------------------------
KNOWN_SAMPLE_RATES = {8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000}
_RATE_RE = re.compile(r"\b(8000|11025|16000|22050|24000|32000|44100|48000)\b")
_RATE_K_RE = re.compile(r"\b(8|16|22|24|32|48)k(?:hz)?\b")
_NAMED_PARAM_RE = re.compile(
    r"(n_fft|fft_size|frame_size|frame_len|frame_length|hop_size|hop_length|"
    r"win_len|win_length|window_size|chunk_size|buffer_size|n_mels|mel_bins|"
    r"num_mel|bit_rate|bitrate|sample_rate|samplerate|num_channels)"
    r"\D{0,3}(\d{2,6})")
_CHANNELS_RE = re.compile(r"\b(mono|stereo)\b")
CODECS = ["opus", "aac", "pcm", "flac", "vorbis", "amr", "mp3"]

_PARAM_CANON = {
    "samplerate": "sample_rate", "fft_size": "n_fft",
    "frame_len": "frame_size", "frame_length": "frame_size",
    "hop_size": "hop_length", "win_len": "win_length",
    "window_size": "win_length", "mel_bins": "n_mels", "num_mel": "n_mels",
    "bit_rate": "bitrate", "num_channels": "channels",
}


def extract_audio_parameters(ascii_text):
    """Parameter vocabulary visible in one module's strings."""
    params = defaultdict(set)

    for name, value in _NAMED_PARAM_RE.findall(ascii_text):
        params[_PARAM_CANON.get(name, name)].add(int(value))

    for rate in _RATE_RE.findall(ascii_text):
        params["sample_rate"].add(int(rate))
    for k in _RATE_K_RE.findall(ascii_text):
        rate = int(float(k) * 1000)
        if rate in KNOWN_SAMPLE_RATES:
            params["sample_rate"].add(rate)

    channels = set(_CHANNELS_RE.findall(ascii_text))
    if channels:
        params["channel_layout"] = channels

    codecs = {c for c in CODECS if c in ascii_text}
    if codecs:
        params["codecs"] = codecs

    return {k: sorted(v) for k, v in params.items()}


def detect_stage_operations(ascii_text, i18n_text):
    """Which stages a module participates in, with the operations seen."""
    stages = {}
    for stage, ops in STAGE_OPERATIONS.items():
        found = sorted({op for op in ops
                        if op in ascii_text or op in i18n_text})
        if found:
            stages[stage] = found
    return stages


def infer_task(ascii_text, i18n_text):
    for task, kws in INFERENCE_TASKS:
        if any(k in ascii_text or k in i18n_text for k in kws):
            return task
    return "audio_processing"


# ---------------------------------------------------------------------------
# Chain construction
# ---------------------------------------------------------------------------
def parameter_transitions(chain):
    """Where the same parameter carries different values in successive
    stages, record the change -- the observable trace of resampling,
    downmixing, or framing between capture and model input."""
    by_stage = defaultdict(lambda: defaultdict(set))
    for entry in chain:
        for param, values in entry.get("parameters", {}).items():
            by_stage[param][entry["stage"]].update(
                values if isinstance(values, list) else [values])

    transitions = []
    for param, stages in by_stage.items():
        seen = [(s, sorted(stages[s])) for s in STAGE_ORDER if s in stages]
        for (s1, v1), (s2, v2) in zip(seen, seen[1:]):
            if v1 != v2:
                transitions.append({"parameter": param,
                                    "from_stage": s1, "from": v1,
                                    "to_stage": s2, "to": v2})
    return transitions


def trace_listening(files, permissions=None, dex_urls=None):
    """Trace audio inputs, parameters, and outputs for one app.

    :param files: iterable of (name, bytes) -- native libs and assets
    :param permissions: manifest permissions (corroboration only)
    :param dex_urls: optional URL strings from the app's DEX (Java/Kotlin)
        code. Audio upload/streaming/transcription backends typically live
        here, not in native libraries, so without this a recorder or music
        app shows no endpoints. Library boilerplate is filtered; each
        endpoint is tagged audio_related.
    :returns: dict -- sources, chain, parameter_transitions, summary
    """
    permissions = set(permissions or [])
    cso, curl, cmodel = ClassifySO(), ClassifyURL(), ClassifyModel()

    modules, models = [], []
    for name, data in files:
        if looks_like_model(name):
            models.append((name, data))
        elif name.endswith(".so"):
            modules.append((name, data))

    sources = {}
    chain = []
    endpoints = []
    module_views = {}

    for name, data in modules:
        strings, ascii_text, i18n_text = make_text_views(cso, data)
        stages = detect_stage_operations(ascii_text, i18n_text)

        # Audio-relevance gate: at least two distinct stage operations,
        # or one operation plus an evidenced audio source. One generic
        # hit ("fft" in a graphics library) is not enough.
        source_hits = {}
        for source_id, sig in AUDIO_SOURCES.items():
            score, ev = find_evidence(sig, ascii_text, i18n_text, permissions)
            if score >= 2:
                source_hits[source_id] = (score, ev)

        total_ops = sum(len(v) for v in stages.values())
        if total_ops < 2 and not source_hits:
            continue

        vendor = cso.detect_vendor(name, strings)
        params = extract_audio_parameters(ascii_text)
        module_views[name] = (ascii_text, i18n_text)

        for source_id, (score, ev) in source_hits.items():
            entry = sources.setdefault(source_id, {"modules": [],
                                                   "evidence": {}})
            entry["modules"].append(name)
            entry["evidence"][name] = ev

        for stage in STAGE_ORDER:
            if stage not in stages:
                continue
            entry = {
                "stage": stage,
                "module": name,
                "vendor": vendor,
                "operations": stages[stage],
            }
            stage_params = dict(params) if stage != "output" else {}
            if stage_params:
                entry["parameters"] = stage_params
            if stage == "inference":
                entry["task"] = infer_task(ascii_text, i18n_text)
            chain.append(entry)

        # onward: endpoints reachable from this audio module (native strings)
        for url_info in curl.find_urls_with_analysis(strings):
            target = url_info["domain"] + url_info["template"]
            if is_noise_endpoint(target):
                continue
            endpoints.append({
                "stage": "output",
                "module": name,
                "kind": "endpoint",
                "source_layer": "native",
                "target": target,
                "categories": url_info["categories"],
                "audio_related": bool(AUDIO_ENDPOINT_HINT.search(target)),
            })

    # onward (dex): audio backends live in Java/Kotlin, not native libs.
    # Filter library boilerplate (DoH, analytics, schema URLs) and tag
    # whether each endpoint looks audio-related so a transcription/upload
    # host stands out from a generic telemetry call.
    if dex_urls:
        seen_dex = set()
        for url in dex_urls:
            dom = curl.get_domain_safe(url)
            if not dom or is_noise_endpoint(url):
                continue
            target = dom + curl.generate_template(url)
            if target in seen_dex or is_noise_endpoint(target):
                continue
            seen_dex.add(target)
            endpoints.append({
                "stage": "output",
                "module": "app_code",
                "kind": "endpoint",
                "source_layer": "dex",
                "target": target,
                "categories": curl.classify_url(url),
                "audio_related": bool(AUDIO_ENDPOINT_HINT.search(url)),
            })

    # audio models referenced by name from an audio module's strings
    for mname, mdata in models:
        base = mname.rsplit("/", 1)[-1].lower()
        stem = base.rsplit(".", 1)[0]
        toks = [t for t in re.split(r"[^a-z0-9]+", stem)
                if len(t) >= 4 and not re.fullmatch(r"v?\d+|q\d+|fp\d+|int\d+", t)]
        refs = [n for n, (a, i) in module_views.items()
                if base in (a + i) or (len(stem) >= 4 and stem in (a + i))
                or any(t in (a + i) for t in toks)]
        if not refs:
            # unreferenced audio model: still record it as an inference node
            # so the chain shows the model exists, just unlinked
            info = cmodel.classify(mname, mdata)
            if info["modality"] in ("audio", "unknown"):
                chain.append({"stage": "inference", "model": mname,
                              "format": info["format"], "vendor": info["vendor"],
                              "referenced_by": [], "linked": False,
                              "task": "audio_processing"})
            continue
        context = " ".join(module_views[r][0] for r in refs)
        info = cmodel.classify(mname, mdata, context_text=context)
        if info["modality"] not in ("audio", "unknown"):
            continue
        chain.append({
            "stage": "inference",
            "model": mname,
            "format": info["format"],
            "vendor": info["vendor"],
            "referenced_by": refs,
            "task": infer_task(" ".join(module_views[r][0] for r in refs),
                               " ".join(module_views[r][1] for r in refs)),
        })

    chain.sort(key=lambda e: STAGE_ORDER.index(e["stage"]))
    chain.extend(endpoints)

    return {
        "sources": {k: {"modules": v["modules"], "evidence": v["evidence"]}
                    for k, v in sources.items()},
        "chain": chain,
        "parameter_transitions": parameter_transitions(chain),
        "summary": {
            "sources": sorted(sources),
            "stages_present": sorted({e["stage"] for e in chain},
                                     key=STAGE_ORDER.index),
            "inference_tasks": sorted({e["task"] for e in chain
                                       if e["stage"] == "inference"}),
            "endpoints": sorted({e["target"] for e in endpoints})[:20],
            "audio_endpoints": sorted({e["target"] for e in endpoints
                                       if e.get("audio_related")})[:20],
            "endpoints_from_dex": sum(1 for e in endpoints
                                      if e.get("source_layer") == "dex"),
            "audio_modules": len(module_views),
        },
    }
