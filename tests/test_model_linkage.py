"""
Regression tests for the model-detection and model-linkage fixes:
real-world apps (not the seeded Otter/TikTok vocabulary) must produce
sources, links, and linked models.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.multimodal_pipeline import (
    build_flow_graph, looks_like_model)
from cim_app_histories.calls.listening import trace_listening


def so(strings, pad=120000):
    return b"\x00".join(s.encode() if isinstance(s, str) else s
                        for s in strings) + b"\x00" * pad


def test_looks_like_model_accepts_bin_and_assets():
    assert looks_like_model("assets/ggml_model_q4.bin")
    assert looks_like_model("assets/voice_encoder.bin")
    assert looks_like_model("assets/sentencepiece.model")
    assert looks_like_model("lib/arm64/libfoo.tflite")
    # negatives
    assert not looks_like_model("lib/arm64/libfoo.so")
    assert not looks_like_model("assets/config.bin")      # no model hint
    assert not looks_like_model("res/icon.png")


def test_model_links_via_token_when_stem_differs():
    """Filename ggml_model_q4 vs reference ggml_model: token overlap links."""
    files = [("lib/arm64/libx.so", so(["model_loader", "ggml_model.bin",
                                        "inference"])),
             ("assets/ggml_model_q4.bin", b"\x00" * 60000)]
    g = build_flow_graph(files, permissions=["android.permission.INTERNET"])
    uses = [l for l in g["links"] if l["kind"] == "uses_model"]
    assert len(uses) == 1
    assert uses[0]["evidence"]["name_reference"].startswith("token:")
    assert g["summary"]["models_linked"] == 1


def test_unseeded_app_still_produces_sources_and_endpoints():
    """A realistic streaming lib (not seeded vocabulary) must not be blank."""
    files = [("lib/arm64-v8a/liborbit-jni-spotify.so", so([
        "OpenSLES", "createAudioPlayer", "AudioTrack", "libopus",
        "tensorflow", "embedding_lookup", "recommend",
        "https://spclient.wg.spotify.com/recommendations"]))]
    g = build_flow_graph(files, permissions=["android.permission.INTERNET"])
    assert g["links"], "expected non-empty links for a realistic lib"
    assert g["summary"]["endpoints"]


def test_summary_always_reports_model_counts():
    g = build_flow_graph([("assets/m.tflite", b"\x18\x00\x00\x00TFL3"+b"\x00"*9000)],
                         permissions=[])
    assert "models_total" in g["summary"]
    assert g["summary"]["models_total"] == 1


def test_listening_records_unreferenced_audio_model():
    """An audio model with no co-located string ref is still shown,
    flagged linked=False, rather than vanishing."""
    files = [("lib/arm64/libcap.so", so(["AudioRecord", "pcm", "16000"])),
             ("assets/whisper_tiny.onnx", b"\x00" * 40000)]
    r = trace_listening(files, permissions=["android.permission.RECORD_AUDIO"])
    models = [e for e in r["chain"] if e.get("model")]
    assert any("whisper" in m["model"] for m in models)


# --- split App Bundle handling (the real-corpus failure) -------------
def test_boilerplate_models_filtered():
    from cim_app_histories.calls.multimodal_pipeline import looks_like_model
    assert not looks_like_model(
        "assets/mlkit_barcode_models/barcode_ssd_mobilenet_v1.tflite")
    assert not looks_like_model("assets/org/threeten/bp/TZDB.dat")
    assert looks_like_model("assets/asr/encoder.tflite")  # real model still passes


def test_split_apk_siblings_gathered(tmp_path):
    import cim_app_histories.analyse as an
    (tmp_path / "com.example.app.apk").write_bytes(b"x")
    (tmp_path / "com.example.app.config.arm64_v8a.apk").write_bytes(b"x")
    (tmp_path / "split_config.en.apk").write_bytes(b"x")
    sibs = {s.name for s in an.gather_split_apks(
        str(tmp_path / "com.example.app.apk"))}
    assert "com.example.app.config.arm64_v8a.apk" in sibs
    assert "split_config.en.apk" in sibs


# --- DEX URL extraction (chat/streaming backends live in Java, not .so) ---
def test_dex_urls_produce_endpoints():
    """A chat app with no native libs but DEX API URLs must still show
    its backend endpoints (the DeepSeek/Spotify failure)."""
    urls = ["https://api.deepseek.com/v1/chat/completions",
            "https://chat.deepseek.com/api/v0/session"]
    g = build_flow_graph([], permissions=["android.permission.INTERNET"],
                         dex_urls=urls)
    sends = [l for l in g["links"] if l["kind"] == "sends_to"]
    targets = {l["target"] for l in sends}
    assert "api.deepseek.com/v1/chat/completions" in targets
    assert all(l["evidence"]["source_layer"] == "dex" for l in sends)
    assert g["summary"]["endpoints_from_dex"] == 2


def test_dex_endpoint_noise_filtered():
    from cim_app_histories.calls.multimodal_pipeline import is_noise_endpoint
    assert is_noise_endpoint("https://dns.google/dns-query")
    assert is_noise_endpoint("https://www.w3.org/2000/svg")
    assert is_noise_endpoint("https://app-measurement.com/a")
    assert is_noise_endpoint("https://firebase-settings.crashlytics.com/x")
    assert not is_noise_endpoint("https://api.deepseek.com/v1/chat")
    assert not is_noise_endpoint("https://spclient.wg.spotify.com/melody")


def test_dex_noise_excluded_from_graph():
    urls = ["https://api.spotify.com/v1/me/player",
            "https://doh.opendns.com/dns-query",      # noise
            "https://app-measurement.com/a"]          # noise
    g = build_flow_graph([], permissions=[], dex_urls=urls)
    targets = {l["target"] for l in g["links"] if l["kind"] == "sends_to"}
    assert "api.spotify.com/v1/me/player" in targets
    assert not any("dns-query" in t or "measurement" in t for t in targets)
