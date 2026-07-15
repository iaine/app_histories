"""
Stage vocabulary and parameter extraction across all modalities.

The listening workflow models audio as a canonical chain
(capture -> dsp -> features -> inference -> output). This module
generalises that idea to every modality the toolkit traces -- audio,
video, image, text, sensor, location -- so the flows workflow can
report a chain per modality:

    microphone -> capture -> preprocess -> features -> inference -> output
    camera     -> capture -> preprocess -> features -> inference -> output

Vocabulary and parameter patterns are data, not code: extend the
tables here (including non-English terms) as a corpus teaches new
terminology. Keyword matching runs over both an ASCII view and a
tolerant UTF-8 decode so CJK strings are visible.
"""

import re
from collections import defaultdict

# Canonical processing order, shared by every modality. "dsp" from the
# listening workflow generalises to "preprocess" (resize/crop/normalise
# for vision, resample/denoise for audio, tokenise for text).
STAGE_ORDER = ["capture", "preprocess", "features", "inference", "output"]

# Per-modality stage operations. Keys are modality names; values map a
# stage to the keywords that evidence it in a module's strings.
MODALITY_STAGES = {
    "audio": {
        "capture": ["audiorecord", "opensl", "aaudio", "audio_capture",
                    "pcm_in", "recorder", "\u5f55\u97f3"],           # 录音
        "preprocess": ["resample", "downsample", "denoise", "noise_suppress",
                       "aec", "echo_cancel", "agc", "gain_control", "vad",
                       "voice_activity", "beamform", "webrtc_apm", "loudness",
                       "\u964d\u566a", "\u589e\u76ca"],              # 降噪 增益
        "features": ["fft", "stft", "spectrogram", "mel", "mfcc", "fbank",
                     "filterbank", "log_mel", "cepstral", "pitch_", "chroma",
                     "\u9891\u8c31"],                                # 频谱
        "inference": ["asr", "speech_to_text", "wakeword", "hotword",
                      "keyword_spot", "speaker_id", "voiceprint",
                      "\u8bed\u97f3\u8bc6\u522b"],                   # 语音识别
        "output": ["transcript", "subtitle", "caption", "send_audio",
                   "playlist", "next_track", "\u8f6c\u5199"],        # 转写
    },
    "video": {
        "capture": ["camera2", "camerax", "mediarecorder", "preview_frame",
                    "surfacetexture", "videocapture", "\u5f55\u50cf"],  # 录像
        "preprocess": ["demux", "decode", "yuv", "nv21", "rgba_convert",
                       "scale_frame", "frame_rate", "deinterlace",
                       "\u89e3\u7801"],                              # 解码
        "features": ["optical_flow", "keyframe", "motion_vector",
                     "frame_feature", "\u5e27\u7279\u5f81"],          # 帧特征
        "inference": ["face_detect", "object_detect", "pose", "segment",
                      "tracking", "\u4eba\u8138\u68c0\u6d4b"],        # 人脸检测
        "output": ["overlay", "render", "encode_video", "stream_out"],
    },
    "image": {
        "capture": ["imagereader", "bitmap_capture", "screenshot",
                    "mediaprojection", "\u622a\u5c4f"],              # 截屏
        "preprocess": ["resize", "crop", "normalize", "rgb_convert",
                       "letterbox", "\u7f29\u653e"],                  # 缩放
        "features": ["embedding", "descriptor", "keypoint", "histogram",
                     "\u7279\u5f81\u63d0\u53d6"],                     # 特征提取
        "inference": ["classif", "ocr", "detect", "landmark", "beauty",
                      "\u56fe\u50cf\u8bc6\u522b"],                    # 图像识别
        "output": ["bounding_box", "mask", "label", "render_result"],
    },
    "text": {
        "capture": ["inputmethod", "edittext", "keyboard", "clipboard",
                    "\u8f93\u5165\u6cd5"],                           # 输入法
        "preprocess": ["tokenize", "sentencepiece", "wordpiece", "normalize_text",
                       "\u5206\u8bcd"],                              # 分词
        "features": ["embedding", "vocab", "token_id", "\u5411\u91cf"],  # 向量
        "inference": ["bert", "llm", "generate", "sentiment", "translate",
                      "intent", "\u7ffb\u8bd1"],                     # 翻译
        "output": ["completion", "suggestion", "reply", "\u56de\u590d"],  # 回复
    },
    "bluetooth": {
        # A companion device's own chain: discover/pair, open a link,
        # move data across it, then hand off (usually to the audio chain).
        "capture": ["bluetoothlescanner", "startscan", "scanfilter",
                    "companiondevicemanager", "bonded_device", "pairing",
                    "createbond", "\u914d\u5bf9"],                     # 配对
        "preprocess": ["bluetoothgatt", "gattcharacteristic", "notify_value",
                       "rfcomm", "bluetoothsocket", "l2cap", "mtu_",
                       "connectgatt"],
        "features": ["chunk_transfer", "packet_assembl", "opus_frame",
                     "adpcm", "sbc_decode", "codec_negotiat"],
        "inference": ["device_model", "firmware_", "battery_level"],
        "output": ["file_received", "recording_download", "sync_complete",
                   "upload_recording", "\u540c\u6b65"],               # 同步
    },
    "sensor": {
        "capture": ["sensormanager", "accelerometer", "gyroscope", "step_counter",
                    "\u4f20\u611f\u5668"],                           # 传感器
        "preprocess": ["filter_window", "smooth", "calibrat"],
        "features": ["magnitude", "axis_feature", "window_feature"],
        "inference": ["activity_recognit", "gesture", "fall_detect"],
        "output": ["activity_label", "step_count"],
    },
    "location": {
        "capture": ["locationmanager", "fusedlocation", "gps_", "geolocation",
                    "\u5b9a\u4f4d"],                                 # 定位
        "preprocess": ["geofence", "kalman", "snap_to_road"],
        "features": ["geohash", "trajectory", "dwell"],
        "inference": ["place_predict", "mobility", "poi_"],
        "output": ["coordinates", "place_label"],
    },
}

# ClassifyModel labels model assets with its own vocabulary
# (audio / vision / nlp). Those name the same concepts as the stage
# modalities, so map them to one canonical set rather than letting a
# TikTok report both "vision" and "image" as if they were different
# things. "vision" covers still-image work (face, OCR, segmentation);
# where a model is genuinely video-specific the video keywords in
# MODALITY_STAGES pick it up from the library side.
MODALITY_ALIASES = {
    "vision": "image",
    "nlp": "text",
    "speech": "audio",
    "voice": "audio",
}


def canonical_modality(modality):
    """Map any classifier's modality label onto the canonical set."""
    if not modality:
        return "unknown"
    return MODALITY_ALIASES.get(modality.lower(), modality.lower())


# Which device inputs feed which modality (input ids come from
# INPUT_SIGNATURES in multimodal_pipeline).
INPUT_MODALITY = {
    "microphone": "audio",
    # A Bluetooth headset/mic is an audio route: it feeds the same
    # capture -> preprocess -> features chain as the built-in mic.
    "bluetooth_audio": "audio",
    # A companion-device link is its own modality: purpose-built hardware
    # (a Plaud recorder, a wearable) streams over GATT/RFCOMM, which is a
    # transfer path rather than an audio route. Its onward processing is
    # often "receive a file, then run the audio chain on it", so keeping
    # it distinct is what makes that two-step visible.
    "bluetooth_device": "bluetooth",
    "bluetooth_midi": "audio",
    "network_stream": "audio",
    "camera": "video",
    "screen": "image",
    "file": "image",
    "text_input": "text",
    "sensor": "sensor",
    "location": "location",
}

# --------------------------------------------------------------------------
# Parameters, per modality. Named patterns are canonicalised so the same
# concept reads the same across modalities (e.g. width/height -> resolution).
# --------------------------------------------------------------------------
KNOWN_SAMPLE_RATES = {8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000}

# Which parameters are meaningful for which modality. A parameter that is
# not plausible for a modality is not reported for it, even when the same
# library contains it: a WebView library holds location APIs AND a whole
# media stack, and without this scoping the location entries inherited
# fps/bitrate/codecs/sample_rate from the media code (they did: TikTok's
# location capture reported sample_rate=384, codecs=aac).
MODALITY_PARAMS = {
    "audio": {"sample_rate", "channel_layout", "n_fft", "frame_size",
              "hop_length", "win_length", "n_mels", "bitrate", "chunk_size",
              "buffer_size", "codecs", "num_threads",
              "bt_profile", "bt_codecs"},
    "video": {"resolution", "fps", "bitrate", "codecs", "num_threads",
              "batch_size"},
    "image": {"resolution", "image_size", "input_width", "input_height",
              "codecs", "num_threads", "batch_size", "embedding_dim"},
    "text": {"max_length", "max_tokens", "vocab_size", "embedding_dim",
             "hidden_size", "batch_size", "num_threads"},
    "sensor": {"sampling_period", "window_size", "win_length", "batch_size"},
    "location": {"sampling_period"},
    # A BT link's own parameters: negotiated codec, MTU/packet size, and
    # the sample rate an SCO/A2DP route runs at.
    "bluetooth": {"codecs", "sample_rate", "chunk_size", "buffer_size",
                  "bitrate", "channel_layout"},
}

_NAMED_PARAM_RE = re.compile(
    r"(n_fft|fft_size|frame_size|frame_len|frame_length|hop_size|hop_length|"
    r"win_len|win_length|window_size|chunk_size|buffer_size|n_mels|mel_bins|"
    r"num_mel|bit_rate|bitrate|sample_rate|samplerate|num_channels|"
    r"input_width|input_height|image_size|input_size|max_length|max_tokens|"
    r"vocab_size|embedding_dim|hidden_size|num_threads|fps|frame_rate|"
    r"sampling_period|batch_size)"
    r"\D{0,3}(\d{2,6})")

_PARAM_CANON = {
    "samplerate": "sample_rate", "fft_size": "n_fft",
    "frame_len": "frame_size", "frame_length": "frame_size",
    "hop_size": "hop_length", "win_len": "win_length",
    "window_size": "win_length", "mel_bins": "n_mels", "num_mel": "n_mels",
    "bit_rate": "bitrate", "num_channels": "channels",
    "frame_rate": "fps", "input_size": "image_size",
}

_RATE_RE = re.compile(r"\b(8000|11025|16000|22050|24000|32000|44100|48000)\b")
_RATE_K_RE = re.compile(r"\b(8|16|22|24|32|48)k(?:hz)?\b")
_CHANNELS_RE = re.compile(r"\b(mono|stereo)\b")

# Bluetooth audio profiles. SCO/HFP: 8/16 kHz bidirectional voice — the only
# route that carries a microphone. A2DP: one-way playback to a speaker or
# headphone. Distinguishing them is what stops "app talks to a BT speaker"
# being read as "app captures from a BT mic".
_BT_SCO_RE = re.compile(
    r"(startbluetoothsco|setbluetoothscoon|bluetoothsco|sco_audio|"
    r"type_bluetooth_sco|bluetoothheadset|\bhfp\b|\bhsp\b|"
    r"isbluetoothscoavailableoffcall|setcommunicationdevice)", re.I)
_BT_A2DP_RE = re.compile(
    r"(bluetootha2dp|\ba2dp\b|type_bluetooth_a2dp|\bavrcp\b)", re.I)
# Codecs specific to a Bluetooth link (distinct from file/container codecs).
_BT_CODECS = ["sbc", "msbc", "cvsd", "aptx", "aptx_hd", "ldac", "lc3", "aac_bt"]
_RESOLUTION_RE = re.compile(r"\b(\d{3,4})\s*[x\u00d7]\s*(\d{3,4})\b")
_CODECS = ["opus", "aac", "pcm", "flac", "vorbis", "amr", "mp3",
           "h264", "h265", "hevc", "vp8", "vp9", "av1", "jpeg", "png", "webp"]


def extract_parameters(ascii_text, modality=None):
    """Parameter vocabulary visible in one module's strings.

    Returns a dict of parameter -> sorted values. Only patterns that are
    meaningful for the modality are reported when ``modality`` is given
    (a sample rate in a vision library is usually a coincidence), keeping
    the chain honest rather than sprinkling audio parameters everywhere.
    """
    params = defaultdict(set)

    for name, value in _NAMED_PARAM_RE.findall(ascii_text):
        params[_PARAM_CANON.get(name, name)].add(int(value))

    if modality in (None, "audio"):
        for rate in _RATE_RE.findall(ascii_text):
            params["sample_rate"].add(int(rate))
        for k in _RATE_K_RE.findall(ascii_text):
            rate = int(float(k) * 1000)
            if rate in KNOWN_SAMPLE_RATES:
                params["sample_rate"].add(rate)
        ch = set(_CHANNELS_RE.findall(ascii_text))
        if ch:
            params["channel_layout"] = ch

    if modality in (None, "audio"):
        prof = set()
        if _BT_SCO_RE.search(ascii_text):
            prof.add("sco")
        if _BT_A2DP_RE.search(ascii_text):
            prof.add("a2dp")
        if prof:
            params["bt_profile"] = prof
        bt_c = {c for c in _BT_CODECS
                if re.search(r"\b" + re.escape(c) + r"\b", ascii_text)}
        if bt_c:
            params["bt_codecs"] = bt_c

    if modality in (None, "video", "image"):
        res = {f"{w}x{h}" for w, h in _RESOLUTION_RE.findall(ascii_text)}
        if res:
            params["resolution"] = res

    codecs = {c for c in _CODECS if c in ascii_text}
    if codecs:
        params["codecs"] = codecs

    allowed = MODALITY_PARAMS.get(modality) if modality else None
    return {k: sorted(v) for k, v in params.items()
            if allowed is None or k in allowed}


def detect_stages(ascii_text, i18n_text, modality):
    """Stages of ``modality`` that a module participates in, with the
    operations observed. Returns {stage: [operations]}."""
    table = MODALITY_STAGES.get(modality, {})
    stages = {}
    for stage, ops in table.items():
        found = sorted({op for op in ops
                        if op in ascii_text or op in i18n_text})
        if found:
            stages[stage] = found
    return stages


def parameter_transitions(chain):
    """Where a parameter carries different values in successive stages of
    the same modality, record the change (e.g. sample_rate 48000 at
    capture, 16000 at features: the resample-for-inference signature)."""
    by_mod = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for entry in chain:
        mod = entry.get("modality", "unknown")
        for param, values in (entry.get("parameters") or {}).items():
            vals = values if isinstance(values, list) else [values]
            by_mod[mod][param][entry["stage"]].update(vals)

    out = []
    for mod, params in by_mod.items():
        for param, stages in params.items():
            seen = [(s, sorted(stages[s])) for s in STAGE_ORDER if s in stages]
            for (s1, v1), (s2, v2) in zip(seen, seen[1:]):
                if v1 != v2:
                    out.append({"modality": mod, "parameter": param,
                                "from_stage": s1, "from": v1,
                                "to_stage": s2, "to": v2})
    return out


def extract_parameters_by_stage(ascii_text, modality, stages, window=200):
    """Attribute each parameter occurrence to its NEAREST stage.

    A module's whole string table usually contains every parameter it ever
    uses (capture at 48 kHz and features at 16 kHz both appear), so
    reporting the module-wide set on every stage hides the change that
    matters. Each parameter occurrence is assigned to whichever stage's
    operation keyword sits closest to it, so capture keeps 48000 and
    features keeps 16000 -- which is what makes a transition detectable.
    Stages with no nearby parameter fall back to the module-wide set.

    Static caveat: nearness in a string table is a proxy for pipeline
    position, not proof of it. Treat stage-attributed parameters as
    candidates to audit, like every other signal in this toolkit.
    """
    # positions of each stage's operation keywords
    stage_pos = {}
    for stage, ops in stages.items():
        pos = []
        for op in ops:
            pos.extend(m.start() for m in re.finditer(re.escape(op), ascii_text))
        if pos:
            stage_pos[stage] = pos

    if not stage_pos:
        return {s: {} for s in stages}

    def nearest_stage(idx):
        best, best_d = None, None
        for stage, positions in stage_pos.items():
            d = min(abs(idx - p) for p in positions)
            if best_d is None or d < best_d:
                best, best_d = stage, d
        return best if best_d is not None and best_d <= window else None

    per_stage = {s: {} for s in stages}
    # walk parameter occurrences, assigning each to its nearest stage
    for m in _NAMED_PARAM_RE.finditer(ascii_text):
        stage = nearest_stage(m.start())
        if stage:
            key = _PARAM_CANON.get(m.group(1), m.group(1))
            per_stage[stage].setdefault(key, set()).add(int(m.group(2)))

    if modality in (None, "audio"):
        for m in _RATE_RE.finditer(ascii_text):
            stage = nearest_stage(m.start())
            if stage:
                per_stage[stage].setdefault("sample_rate", set()).add(int(m.group(1)))
        for m in _CHANNELS_RE.finditer(ascii_text):
            stage = nearest_stage(m.start())
            if stage:
                per_stage[stage].setdefault("channel_layout", set()).add(m.group(1))

    if modality in (None, "audio"):
        for rx, val in ((_BT_SCO_RE, "sco"), (_BT_A2DP_RE, "a2dp")):
            for m in rx.finditer(ascii_text):
                stage = nearest_stage(m.start())
                if stage:
                    per_stage[stage].setdefault("bt_profile", set()).add(val)
        for c in _BT_CODECS:
            for m in re.finditer(r"\b" + re.escape(c) + r"\b", ascii_text):
                stage = nearest_stage(m.start())
                if stage:
                    per_stage[stage].setdefault("bt_codecs", set()).add(c)

    if modality in (None, "video", "image"):
        for m in _RESOLUTION_RE.finditer(ascii_text):
            stage = nearest_stage(m.start())
            if stage:
                per_stage[stage].setdefault(
                    "resolution", set()).add(f"{m.group(1)}x{m.group(2)}")

    # No module-wide fallback: if no parameter occurs near this stage's own
    # operations, report none. Falling back to the whole binary's parameters
    # made a WebView library (location APIs + a full media stack) report
    # sample_rate/fps/codecs on its location stages -- borrowed numbers that
    # were never evidence about location at all.
    # Route-level facts: not stage-local. A Bluetooth profile/codec
    # characterises the whole link, so it belongs on every stage of the
    # modality rather than only where the string happens to sit. (Values
    # that genuinely change along the chain -- sample_rate, resolution --
    # stay proximity-attributed above.)
    route = {}
    if modality in (None, "audio"):
        whole = extract_parameters(ascii_text, modality)
        for k in ("bt_profile", "bt_codecs"):
            if k in whole:
                route[k] = set(whole[k])

    allowed = MODALITY_PARAMS.get(modality) if modality else None
    out = {}
    for stage in stages:
        found = dict(per_stage.get(stage) or {})
        for k, v in route.items():
            found.setdefault(k, set()).update(v)
        out[stage] = {k: sorted(v) for k, v in found.items()
                      if allowed is None or k in allowed}
    return out
