"""
Tests for the public notebook/script wrappers in cim_app_histories.analyse.
These exercise the wiring (split merge, dex-url extraction, graph/listening
assembly) with androguard faked, so no real APK is needed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cim_app_histories.analyse as an


def so(strings, pad=60000):
    return b"\x00".join(s.encode() if isinstance(s, str) else s
                        for s in strings) + b"\x00" * pad


class FakeAPK:
    """Minimal stand-in for androguard APK used by the wrappers."""
    def __init__(self, files, perms, urls, pkg="com.x", ver="1.0",
                 dex_inputs=None):
        self._files = files          # {name: bytes}
        self._perms = perms
        self._urls = urls
        self._pkg, self._ver = pkg, ver
        self._dex_inputs = dex_inputs or {}
    def get_files(self): return list(self._files)
    def get_file(self, n): return self._files[n]
    def get_permissions(self): return self._perms
    def get_package(self): return self._pkg
    def get_androidversion_name(self): return self._ver


def patch(monkeypatch, apk):
    monkeypatch.setattr(an, "collect_all_files",
                        lambda p: (apk, an.collect_apk_files(apk),
                                   {"native_libs": 1, "splits_merged": [],
                                    "incomplete_base_apk": False}))
    monkeypatch.setattr(an, "extract_dex_urls", lambda a: a._urls)
    monkeypatch.setattr(an, "extract_dex_inputs", lambda a: a._dex_inputs)


def test_analyse_flows_includes_dex_endpoints(monkeypatch):
    apk = FakeAPK(
        {"lib/arm64/libx.so": so(["OpenSLES", "tensor", "inference"])},
        ["android.permission.INTERNET"],
        ["https://api.deepseek.com/v1/chat/completions"])
    patch(monkeypatch, apk)
    g = an.analyse_flows("whatever.apk")
    targets = {l["target"] for l in g["links"] if l["kind"] == "sends_to"}
    assert "api.deepseek.com/v1/chat/completions" in targets
    assert "sankey" in g and "summary" in g


def test_analyse_listening_includes_dex_and_app_meta(monkeypatch):
    apk = FakeAPK(
        {"lib/arm64/libaudio.so": so(["AudioRecord", "pcm", "16000", "vad"])},
        ["android.permission.RECORD_AUDIO"],
        ["https://api.plaud.ai/v1/transcribe/upload"],
        pkg="ai.plaud.android", ver="3.9")
    patch(monkeypatch, apk)
    r = an.analyse_listening("whatever.apk")
    eps = {e["target"] for e in r["chain"] if e.get("kind") == "endpoint"}
    assert "api.plaud.ai/v1/transcribe/upload" in eps
    assert r["app"]["pkg"] == "ai.plaud.android"
    assert "microphone" in r["sources"]


def test_incomplete_base_warning(monkeypatch):
    apk = FakeAPK({}, [], [])
    monkeypatch.setattr(an, "collect_all_files",
                        lambda p: (apk, [], {"native_libs": 0,
                                             "splits_merged": [],
                                             "incomplete_base_apk": True}))
    monkeypatch.setattr(an, "extract_dex_urls", lambda a: [])
    g = an.analyse_flows("base.apk")
    assert "warning" in g and "split App Bundle" in g["warning"]


def test_pkg_version_available_for_gephi(monkeypatch):
    """Gephi's node table reads per-node attributes. pkg/version must be
    on every node, plus flat top-level and nested 'app', so a converter
    finds them wherever it looks."""
    apk = FakeAPK(
        {"lib/arm64/libx.so": so(["audiorecord", "asr"])},
        ["android.permission.RECORD_AUDIO"], [], pkg="com.demo", ver="2.5")
    patch(monkeypatch, apk)
    g = an.analyse_flows("x.apk")
    assert g["pkg"] == "com.demo" and g["version"] == "2.5"        # flat
    assert g["app"] == {"pkg": "com.demo", "version": "2.5"}       # nested
    assert g["nodes"], "expected nodes"
    for n in g["nodes"]:                                           # per-node
        assert n["pkg"] == "com.demo" and n["version"] == "2.5"


def test_dex_audio_input_creates_microphone_without_native_lib(monkeypatch):
    """The Otter case: an app that records via AudioRecord in Java/Kotlin
    and ships NO audio native library must still show the microphone
    input, evidenced by the DEX API call and attributed to app_code."""
    apk = FakeAPK(
        {"lib/arm64/libimage_processing_util_jni.so": so(["scale", "crop"])},
        ["android.permission.RECORD_AUDIO"],
        [],
        dex_inputs={"microphone": ["AudioRecord"]})
    patch(monkeypatch, apk)
    g = an.analyse_flows("x.apk")
    assert "microphone" in g["summary"]["inputs"]
    mic = [l for l in g["links"] if l["source"] == "microphone"]
    assert mic and mic[0]["target"] == "app_code"
    assert mic[0]["evidence"]["dex_api"] == ["AudioRecord"]
    # permission corroborates but is recorded as such
    assert mic[0]["evidence"]["permissions"] == ["android.permission.RECORD_AUDIO"]


def test_dex_audio_input_links_without_permission(monkeypatch):
    """The API call is the evidence; the link must appear even when the
    permission is absent (a permission never creates a link, and its
    absence must not suppress real API evidence)."""
    apk = FakeAPK(
        {"lib/arm64/libx.so": so(["scale"])}, [], [],
        dex_inputs={"microphone": ["AudioRecord"]})
    patch(monkeypatch, apk)
    g = an.analyse_flows("x.apk")
    mic = [l for l in g["links"] if l["source"] == "microphone"]
    assert mic, "API-call evidence must link even with no permission"
    assert "permissions" not in mic[0]["evidence"]


def test_no_dex_inputs_no_microphone(monkeypatch):
    """A permission with no capture API call must NOT create the input."""
    apk = FakeAPK(
        {"lib/arm64/libx.so": so(["scale"])},
        ["android.permission.RECORD_AUDIO"], [], dex_inputs={})
    patch(monkeypatch, apk)
    g = an.analyse_flows("x.apk")
    assert "microphone" not in g["summary"]["inputs"]
