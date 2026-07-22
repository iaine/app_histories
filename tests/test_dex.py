"""
Unit testing dex methods
"""
import importlib
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

PACKAGE = "cim_app_histories"

THIRD_PARTY = {
    "androguard", "pandas", "matplotlib", "networkx",
    "numpy", "PIL", "loguru",
}

def _import_or_skip(module_name):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        missing_root = (e.name or "").split(".")[0]
        if missing_root in THIRD_PARTY:
            pytest.skip(f"third-party dependency not installed: {e.name}")
        pytest.fail(f"cannot import {module_name}: {e}")
    except Exception as e:
        pytest.fail(f"cannot import {module_name}: {type(e).__name__}: {e}")

@pytest.mark.skip(reason="waiting for mock to appear")
def test_apk_software_version_semantic():
    mod = _import_or_skip(f"{PACKAGE}.dex.dex")
    ap = mod.extractDEX("filenm")
    assert len(ap.get_methods() ) > 0


# --- DEX-based audio-capture input detection -------------------------
class _Ins:
    def __init__(self, name, out): self._n, self._o = name, out
    def get_name(self): return self._n
    def get_output(self): return self._o


class _Method:
    def __init__(self, ins, cls="Lcom/app/A;"):
        self._ins, self._cls = ins, cls
    def get_code(self): return object() if self._ins else None
    def get_instructions(self): return self._ins
    def get_class_name(self): return self._cls


class _StubDex:
    def __init__(self, methods): self._m = methods
    def get_methods(self): return self._m


def _analyser(methods):
    from cim_app_histories.dex.dex import analyseDEX
    a = analyseDEX.__new__(analyseDEX)   # skip __init__ (needs real bytes)
    a.dex = _StubDex(methods)
    return a


def test_audio_inputs_detects_audiorecord_invoke():
    a = _analyser([_Method([
        _Ins("invoke-virtual",
             "v2, Landroid/media/AudioRecord;->startRecording()V")])])
    assert a.audio_inputs() == {"microphone": {"AudioRecord"}}


def test_audio_inputs_ignores_class_name_as_string_constant():
    """A bare class name as a const-string is a mention, not a call, and
    must not count as evidence."""
    a = _analyser([_Method([
        _Ins("const-string", "v5, 'Landroid/media/AudioRecord;'")])])
    assert a.audio_inputs() == {}


def test_audio_inputs_ignores_audio_playback():
    """AudioTrack is playback (output), not capture -- must not fire."""
    a = _analyser([_Method([
        _Ins("invoke-virtual", "v4, Landroid/media/AudioTrack;->play()V")])])
    assert a.audio_inputs() == {}


def test_audio_inputs_detects_mediarecorder():
    a = _analyser([_Method([
        _Ins("invoke-direct", "v1, Landroid/media/MediaRecorder;-><init>()V")])])
    assert a.audio_inputs() == {"microphone": {"MediaRecorder"}}


def test_extract_dex_inputs_unions_across_dex(monkeypatch):
    """extract_dex_inputs unions capture evidence across every classes*.dex,
    mirroring extract_dex_urls. One dex records, the other doesn't."""
    import cim_app_histories.analyse as an
    import cim_app_histories.dex.dex as realdex

    class FakeAnalyse:
        def __init__(self, b): self._b = b
        def audio_inputs(self):
            return {"microphone": {"AudioRecord"}} if self._b == b"dex1" else {}

    class FakeAPK:
        def get_all_dex(self): return [b"dex1", b"dex2"]

    # extract_dex_inputs does `from .dex.dex import analyseDEX` at call time,
    # so patch the class on the dex.dex module it looks up.
    monkeypatch.setattr(realdex, "analyseDEX", FakeAnalyse)
    assert an.extract_dex_inputs(FakeAPK()) == {"microphone": ["AudioRecord"]}


# --- capture -> egress trace ------------------------------------------
_CAP = "v2, Landroid/media/AudioRecord;->startRecording()V"
_NET = "v3, Lokhttp3/OkHttpClient;->newCall(...)"


def test_trace_egress_method_proximity_is_strongest():
    """One method calling BOTH capture and network is the strongest
    co-occurrence signal the scan can produce."""
    a = _analyser([_Method([_Ins("invoke-virtual", _CAP),
                            _Ins("invoke-virtual", _NET)])])
    r = a.trace_capture_egress()["microphone"]
    assert r["capture"] == ["AudioRecord"]
    assert r["output"] == ["okhttp3"]
    assert r["proximity"] == "method"


def test_trace_egress_class_proximity_when_split_across_methods():
    """Capture and egress in different methods of the SAME class is a
    weaker but real signal."""
    a = _analyser([
        _Method([_Ins("invoke-virtual", _CAP)], cls="Lcom/app/Rec;"),
        _Method([_Ins("invoke-virtual", _NET)], cls="Lcom/app/Rec;")])
    assert a.trace_capture_egress()["microphone"]["proximity"] == "class"


def test_trace_egress_none_when_unrelated_classes():
    """Otter's real shape: recording and uploading live in different
    classes, so both APIs are present but proximity is None. The result
    must say so rather than implying a connection."""
    a = _analyser([
        _Method([_Ins("invoke-virtual", _CAP)], cls="Lcom/app/Rec;"),
        _Method([_Ins("invoke-virtual", _NET)], cls="Lcom/app/Net;")])
    r = a.trace_capture_egress()["microphone"]
    assert r["proximity"] is None
    assert r["output"] == ["okhttp3"]


def test_trace_egress_empty_without_capture():
    """No capture API means nothing to trace, even if the app networks."""
    a = _analyser([_Method([_Ins("invoke-virtual", _NET)])])
    assert a.trace_capture_egress() == {}


def test_trace_egress_ignores_string_constants():
    """As with audio_inputs: a mention is not a call."""
    a = _analyser([_Method([
        _Ins("const-string", "v1, 'Landroid/media/AudioRecord;'"),
        _Ins("const-string", "v2, 'Lokhttp3/OkHttpClient;'")])])
    assert a.trace_capture_egress() == {}
