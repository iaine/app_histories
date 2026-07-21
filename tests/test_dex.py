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
    def __init__(self, ins): self._ins = ins
    def get_code(self): return object() if self._ins else None
    def get_instructions(self): return self._ins


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
