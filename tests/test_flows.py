"""
Tests for the rewritten multimodal flow-graph pipeline.

The contract under test: links are evidence-gated (no cross products),
Chinese keywords are detected in raw binaries, model links require a
name reference in the host library's strings, and the output is pure
data with chains excluded.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.multimodal_pipeline import (
    build_flow_graph, to_sankey, INPUT_SIGNATURES,
)
from cim_app_histories.classify.classify_model import ClassifyModel


def so(strings, pad=60000):
    """Synthesise a .so-ish binary from mixed ASCII/Chinese strings."""
    return b"\x00".join(
        s.encode("utf-8") if isinstance(s, str) else s for s in strings
    ) + b"\x00" * pad


SPEECH_LIB = ("lib/arm64/libttspeech.so", so([
    "android/media/audiorecord", "pcm_in", "\u9ea6\u514b\u98ce",  # 麦克风
    "speech_to_text", "\u8f6c\u5199",                              # 转写
    "tensor", "interpreter", "inference", "model",
    "asr_v3.tflite",
    "https://speech.example.com/v1/upload/audio",
]))
BEAUTY_LIB = ("lib/arm64/libbeauty.so", so([
    "camera2", "preview_frame", "\u6444\u50cf\u5934",              # 摄像头
    "\u4eba\u8138", "landmark",                                    # 人脸
    "tensor", "inference", "interpreter", "predict",
]))
CODEC_LIB = ("lib/arm64/libvpxdec.so", so([
    "decode", "frame", "bitstream", "packet",
]))
MODEL = ("assets/asr_v3.tflite", b"\x18\x00\x00\x00TFL3" + b"\x00" * 70000)
ORPHAN_MODEL = ("assets/orphan.onnx", b"\x08\x01" + b"\x00" * 70000)

PERMS = ["android.permission.RECORD_AUDIO", "android.permission.CAMERA",
         "android.permission.INTERNET"]


@pytest.fixture(scope="module")
def graph():
    return build_flow_graph(
        [SPEECH_LIB, BEAUTY_LIB, CODEC_LIB, MODEL, ORPHAN_MODEL],
        permissions=PERMS,
    )


def links_of(graph, kind):
    return [l for l in graph["links"] if l["kind"] == kind]


def test_microphone_feeds_speech_lib_with_evidence(graph):
    feeds = links_of(graph, "feeds")
    mic = [l for l in feeds if l["source"] == "microphone"]
    assert len(mic) == 1 and mic[0]["target"] == SPEECH_LIB[0]
    ev = mic[0]["evidence"]
    assert "\u9ea6\u514b\u98ce" in ev["keywords"]          # Chinese matched
    assert "android/media/audiorecord" in ev["apis"]       # API = strong
    assert "android.permission.RECORD_AUDIO" in ev["permissions"]
    assert mic[0]["score"] >= 4


def test_camera_feeds_beauty_lib_not_speech_lib(graph):
    cam = [l for l in links_of(graph, "feeds") if l["source"] == "camera"]
    assert [l["target"] for l in cam] == [BEAUTY_LIB[0]]


def test_no_links_without_evidence(graph):
    """The codec lib has no input keywords: it must receive no input link.
    Under the old cross-product behaviour every module got connected."""
    targets = {l["target"] for l in links_of(graph, "feeds")}
    assert CODEC_LIB[0] not in targets


def test_permission_alone_never_creates_link():
    """RECORD_AUDIO is granted app-wide, but a lib with no audio strings
    must not be linked to the microphone."""
    g = build_flow_graph([CODEC_LIB], permissions=PERMS)
    assert links_of(g, "feeds") == []


def test_model_link_requires_name_reference(graph):
    uses = links_of(graph, "uses_model")
    assert {(l["source"], l["target"]) for l in uses} == {
        (SPEECH_LIB[0], MODEL[0])
    }
    # the orphan model exists as a node but is linked to nothing
    node_ids = {n["id"] for n in graph["nodes"]}
    assert ORPHAN_MODEL[0] in node_ids


def test_endpoint_onward_link(graph):
    sends = links_of(graph, "sends_to")
    assert len(sends) == 1 and sends[0]["source"] == SPEECH_LIB[0]
    assert "upload" in sends[0]["evidence"]["url_categories"]


def test_outputs_and_chains_excluded(graph):
    produces = links_of(graph, "produces")
    assert any(l["source"] == SPEECH_LIB[0] and l["target"] == "text"
               for l in produces)
    # chains never appear anywhere in the serialised graph
    import json
    assert '"chain"' not in json.dumps(graph)


def test_sankey_merges_duplicates(graph):
    edges = to_sankey(graph)
    assert len(edges) == len({(e["source"], e["target"]) for e in edges})
    assert all(e["value"] >= 1 for e in edges)


def test_model_classification_i18n():
    cm = ClassifyModel()
    info = cm.classify("assets/\u4eba\u8138_detect.mnn",  # 人脸 face
                       b"\x00" * 100)
    assert info["format"] == "mnn" and info["modality"] == "vision"
    info = cm.classify("assets/asr_v3.tflite", MODEL[1],
                       context_text="\u8bed\u97f3 speech")  # 语音
    assert info["format"] == "tflite" and info["modality"] == "audio"


def test_config_restricts_inputs():
    g = build_flow_graph([SPEECH_LIB], permissions=PERMS,
                         config={"inputs": ["camera"]})
    assert links_of(g, "feeds") == []


def test_pure_and_repeatable():
    a = build_flow_graph([SPEECH_LIB, MODEL], permissions=PERMS)
    b = build_flow_graph([SPEECH_LIB, MODEL], permissions=PERMS)
    assert a == b


def test_every_input_signature_has_chinese():
    """Internationalisation is a contract: each input table must carry at
    least one non-ASCII keyword so English-only drift is caught."""
    for input_id, sig in INPUT_SIGNATURES.items():
        assert any(not k.isascii() for k in sig["keywords"]), input_id
