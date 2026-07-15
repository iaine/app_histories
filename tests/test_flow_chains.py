"""
Tests for the multi-modality staged chain in the flows workflow:
per-modality capture -> preprocess -> features -> inference -> output,
with stage-attributed parameters and detected transitions.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.multimodal_pipeline import build_flow_graph
from cim_app_histories.calls.stages import STAGE_ORDER


def so(strings, pad=120000):
    return b"\x00".join(s.encode() if isinstance(s, str) else s
                        for s in strings) + b"\x00" * pad


AUDIO_LIB = ("lib/arm64/libaudio.so", so([
    "AudioRecord", "android/media/audiorecord", "\u9ea6\u514b\u98ce",
    "sample_rate=48000", "stereo",
    "x" * 400, "resample", "denoise", "vad",
    "x" * 400, "log_mel", "fbank", "sample_rate=16000", "mono", "n_mels 80",
    "x" * 400, "asr", "speech_to_text", "transcript"]))

VIDEO_LIB = ("lib/arm64/libvideo.so", so([
    "camera2", "android/hardware/camera", "\u6444\u50cf\u5934",
    "1920x1080", "preview_frame",
    "x" * 400, "decode", "yuv", "scale_frame", "640x480",
    "x" * 400, "optical_flow",
    "x" * 400, "face_detect",
    "x" * 400, "render"]))

MODEL = ("assets/asr.tflite", b"\x18\x00\x00\x00TFL3" + b"\x00" * 70000)
PERMS = ["android.permission.RECORD_AUDIO", "android.permission.CAMERA",
         "android.permission.INTERNET"]


@pytest.fixture(scope="module")
def graph():
    return build_flow_graph(
        [AUDIO_LIB, VIDEO_LIB, MODEL], permissions=PERMS,
        dex_urls=["https://api.example.net/v1/upload/audio"])


def entries(graph, modality):
    return [e for e in graph["chain"] if e.get("modality") == modality]


def test_separate_chain_per_modality(graph):
    """Audio and video each get their own capture->...->output chain."""
    assert "audio" in graph["summary"]["modalities"]
    assert "video" in graph["summary"]["modalities"]
    audio_stages = [e["stage"] for e in entries(graph, "audio") if e.get("operations")]
    video_stages = [e["stage"] for e in entries(graph, "video") if e.get("operations")]
    for stages in (audio_stages, video_stages):
        assert "capture" in stages and "inference" in stages
        # chain follows canonical order
        idx = [STAGE_ORDER.index(s) for s in stages]
        assert idx == sorted(idx)


def test_operations_are_data_not_nodes(graph):
    """Stage operations live on chain entries; they never become graph
    nodes (no node-per-method explosion)."""
    node_ids = {n["id"] for n in graph["nodes"]}
    for e in graph["chain"]:
        for op in e.get("operations", []):
            assert op not in node_ids


def test_parameters_attached_per_stage(graph):
    cap = [e for e in entries(graph, "audio")
           if e["stage"] == "capture" and e.get("operations")][0]
    assert 48000 in cap["parameters"]["sample_rate"]
    assert "stereo" in cap["parameters"]["channel_layout"]
    feat = [e for e in entries(graph, "audio")
            if e["stage"] == "features" and e.get("operations")][0]
    assert feat["parameters"]["sample_rate"] == [16000]
    assert feat["parameters"]["n_mels"] == [80]


def test_parameter_transitions_detected(graph):
    """The resample-for-inference signature must surface as a transition."""
    ts = graph["parameter_transitions"]
    assert any(t["modality"] == "audio" and t["parameter"] == "sample_rate"
               and 48000 in t["from"] for t in ts)
    assert any(t["modality"] == "video" and t["parameter"] == "resolution"
               for t in ts)


def test_video_resolution_downscale_transition(graph):
    ts = [t for t in graph["parameter_transitions"]
          if t["modality"] == "video" and t["parameter"] == "resolution"]
    assert any("1920x1080" in t["from"] for t in ts)


def test_models_and_endpoints_in_chain(graph):
    models = [e for e in graph["chain"] if e.get("model")]
    assert any("asr.tflite" in m["model"] for m in models)
    eps = [e for e in graph["chain"] if e.get("endpoint")]
    assert any("api.example.net" in e["endpoint"] for e in eps)
    assert all(e["stage"] == "output" for e in eps)


def test_graph_nodes_links_preserved(graph):
    """The node/link graph the viewers consume is unchanged."""
    assert graph["nodes"] and graph["links"]
    assert any(l["kind"] == "feeds" for l in graph["links"])


# --- modality reconciliation and parameter scoping -------------------
def test_vision_and_nlp_map_to_canonical_modalities():
    """ClassifyModel labels models audio/vision/nlp; the stage vocabulary
    uses audio/image/text. One canonical set, so an app never reports
    both 'vision' and 'image' as if they were different things."""
    from cim_app_histories.calls.stages import canonical_modality
    assert canonical_modality("vision") == "image"
    assert canonical_modality("nlp") == "text"
    assert canonical_modality("audio") == "audio"
    assert canonical_modality("image") == "image"
    assert canonical_modality(None) == "unknown"


def test_model_entries_use_canonical_modality():
    face = ("assets/model/ttfacemodel/tt_face_v11.1.model", b"\x00" * 50000)
    lib = ("lib/arm64/libface.so", so(["face_detect", "tt_face_v11.1.model",
                                        "camera2", "preview_frame"]))
    g = build_flow_graph([lib, face], permissions=["android.permission.CAMERA"])
    assert "vision" not in g["summary"]["modalities"]
    models = [e for e in g["chain"] if e.get("model")]
    assert models and all(e["modality"] != "vision" for e in models)


def test_location_does_not_inherit_media_parameters():
    """A WebView library holds location APIs AND a media stack. Location
    stages must not report sample_rate/fps/bitrate/codecs borrowed from
    the media code (TikTok reported sample_rate=384, codecs=aac)."""
    webview = ("lib/arm64/libwebview.so", so([
        "fusedlocation", "geolocation", "locationmanager", "geofence",
        "kalman", "dwell", "trajectory", "coordinates",
        "aac", "h264", "opus", "fps=24", "bitrate=30000",
        "sample_rate=384", "sample_rate=44100"]))
    g = build_flow_graph([webview],
                         permissions=["android.permission.ACCESS_FINE_LOCATION"])
    loc = [e for e in g["chain"] if e.get("modality") == "location"]
    assert loc, "expected location stages"
    for e in loc:
        p = e.get("parameters", {})
        assert "sample_rate" not in p
        assert "fps" not in p
        assert "bitrate" not in p
        assert "codecs" not in p


def test_parameters_scoped_to_modality():
    from cim_app_histories.calls.stages import extract_parameters
    media = "aac h264 fps=24 bitrate=30000 sample_rate=44100 1920x1080"
    assert extract_parameters(media, "location") == {}
    audio = extract_parameters(media, "audio")
    assert "sample_rate" in audio and "resolution" not in audio
    video = extract_parameters(media, "video")
    assert "fps" in video and "resolution" in video
    assert "sample_rate" not in video


def test_no_module_wide_parameter_fallback():
    """A stage with no parameters near its own operations reports none,
    rather than borrowing the binary's unrelated numbers."""
    lib = ("lib/arm64/libmixed.so", so(
        ["locationmanager", "geofence"] + ["x" * 500] +
        ["sample_rate=48000", "mono", "audiorecord", "resample"]))
    g = build_flow_graph([lib], permissions=[])
    loc = [e for e in g["chain"] if e.get("modality") == "location"]
    for e in loc:
        assert not e.get("parameters")
