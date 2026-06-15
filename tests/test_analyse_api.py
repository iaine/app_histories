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
    def __init__(self, files, perms, urls, pkg="com.x", ver="1.0"):
        self._files = files          # {name: bytes}
        self._perms = perms
        self._urls = urls
        self._pkg, self._ver = pkg, ver
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
