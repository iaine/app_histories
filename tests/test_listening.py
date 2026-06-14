"""
Tests for the listening workflow.

Two synthetic apps model the motivating examples: a speech-to-text app
(capture at 48 kHz stereo, DSP, 16 kHz mel features into a TFLite model,
transcript out) and a music-streaming app (stream input, analysis
features, recommendation model, recommendation endpoint).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.listening import (
    trace_listening, extract_audio_parameters, parameter_transitions,
)


def so(strings, pad=60000):
    return b"\x00".join(
        s.encode("utf-8") if isinstance(s, str) else s for s in strings
    ) + b"\x00" * pad


# --- speech-to-text app -----------------------------------------------
STT_CAPTURE = ("lib/arm64/libcapture.so", so([
    "android/media/audiorecord", "pcm_in", "\u9ea6\u514b\u98ce",   # 麦克风
    "sample_rate=48000", "stereo", "buffer_size 3840",
]))
STT_FEATURES = ("lib/arm64/libasrfeat.so", so([
    "resample", "denoise", "vad", "\u964d\u566a",                  # 降噪
    "16000", "mono", "n_fft 512", "hop_length 160", "n_mels 80",
    "log_mel", "fbank",
    "asr_v3.tflite", "interpreter", "speech_to_text",
    "\u8bed\u97f3\u8bc6\u522b",                                    # 语音识别
    "transcript",
    "https://api.stt.example.com/v1/upload/audio",
]))
STT_MODEL = ("assets/asr_v3.tflite", b"\x18\x00\x00\x00TFL3" + b"\x00" * 70000)

# --- music-streaming app ----------------------------------------------
MUSIC_LIB = ("lib/arm64/libplayer.so", so([
    "exoplayer", "hls", "m3u8", "opus", "aac",
    "loudness", "lufs", "tempo", "beat_tracker", "chroma",
    "embedding", "interpreter", "recommend", "playlist", "next_track",
    "https://api.music.example.com/v1/recommendations/next",
]))

CODEC_ONLY = ("lib/arm64/libvpxdec.so", so(["decode", "frame", "bitstream"]))

PERMS = ["android.permission.RECORD_AUDIO", "android.permission.INTERNET"]


@pytest.fixture(scope="module")
def stt():
    return trace_listening([STT_CAPTURE, STT_FEATURES, STT_MODEL, CODEC_ONLY],
                           permissions=PERMS)


@pytest.fixture(scope="module")
def music():
    return trace_listening([MUSIC_LIB], permissions=PERMS)


def stages_of(result, stage):
    return [e for e in result["chain"] if e["stage"] == stage]


# ---------------------------------------------------------------------
def test_microphone_source_with_evidence(stt):
    assert "microphone" in stt["sources"]
    ev = stt["sources"]["microphone"]["evidence"][STT_CAPTURE[0]]
    assert "android/media/audiorecord" in ev["apis"]
    assert "\u9ea6\u514b\u98ce" in ev["keywords"]          # Chinese matched
    assert "android.permission.RECORD_AUDIO" in ev["permissions"]


def test_chain_is_stage_ordered(stt):
    order = ["capture", "dsp", "features", "inference", "output"]
    seen = [e["stage"] for e in stt["chain"]]
    assert seen == sorted(seen, key=order.index)
    assert set(stt["summary"]["stages_present"]) >= {
        "capture", "dsp", "features", "inference", "output"}


def test_parameters_extracted_per_stage(stt):
    cap = stages_of(stt, "capture")[0]
    assert 48000 in cap["parameters"]["sample_rate"]
    assert "stereo" in cap["parameters"]["channel_layout"]
    feat = [e for e in stages_of(stt, "features")
            if e["module"] == STT_FEATURES[0]][0]
    p = feat["parameters"]
    assert p["n_fft"] == [512] and p["hop_length"] == [160]
    assert p["n_mels"] == [80] and 16000 in p["sample_rate"]


def test_sample_rate_transition_capture_to_features(stt):
    """The resample-for-ASR signature: 48 kHz at capture, 16 kHz later."""
    ts = [t for t in stt["parameter_transitions"]
          if t["parameter"] == "sample_rate"]
    assert any(t["from_stage"] == "capture" and 48000 in t["from"]
               and t["to"] == [16000] for t in ts)
    ch = [t for t in stt["parameter_transitions"]
          if t["parameter"] == "channel_layout"]
    assert any(t["from"] == ["stereo"] and t["to"] == ["mono"] for t in ch)


def test_model_linked_and_task_inferred(stt):
    inf = [e for e in stages_of(stt, "inference") if "model" in e]
    assert len(inf) == 1
    assert inf[0]["model"] == STT_MODEL[0]
    assert inf[0]["format"] == "tflite"
    assert inf[0]["referenced_by"] == [STT_FEATURES[0]]
    assert inf[0]["task"] == "speech_to_text"


def test_endpoint_in_output_stage(stt):
    outs = [e for e in stages_of(stt, "output") if e.get("kind") == "endpoint"]
    assert len(outs) == 1
    assert "upload" in outs[0]["categories"]


def test_irrelevant_module_excluded(stt):
    assert all(e.get("module") != CODEC_ONLY[0] for e in stt["chain"])


def test_music_recommendation_flow(music):
    """The Spotify-shaped case: stream in, analysis features, a
    recommendation task, and a recommendation endpoint out."""
    assert "network_stream" in music["sources"]
    assert "music_analysis" in music["summary"]["inference_tasks"]
    feat = stages_of(music, "features")[0]
    assert {"tempo", "chroma"} & set(feat["operations"])
    assert any("recommendations" in e for e in music["summary"]["endpoints"])
    cap = stages_of(music, "capture")
    assert cap == []                       # no microphone claim invented


def test_result_is_json_serialisable_and_chain_free_of_blobs(stt):
    text = json.dumps(stt)
    assert "\\u0000" not in text


def test_parameter_extraction_units():
    p = extract_audio_parameters("sr 16k stereo opus n_mels 40 frame_size 480")
    assert p["sample_rate"] == [16000]
    assert p["n_mels"] == [40] and p["frame_size"] == [480]
    assert p["codecs"] == ["opus"]
    # bare numbers that are not known rates are not invented into rates
    p = extract_audio_parameters("error code 12345 retry 30000")
    assert "sample_rate" not in p


def test_cli_registration_and_json_naming():
    from cim_app_histories.cli import TASKS, make_output_names
    assert "listening" in TASKS
    names = make_output_names([Path("/x/MyApp.apk")], "listening")
    assert list(names.values()) == ["MyApp.listening.json"]
