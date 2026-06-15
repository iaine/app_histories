"""
Tests for analyseDEX.find_built_urls / all_urls: extracting URLs that are
assembled at runtime from fragments (StringBuilder, Uri.Builder, Retrofit,
OkHttp) rather than stored as whole-string literals.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.dex.dex import analyseDEX


class _Ins:
    def __init__(self, name, output): self._n, self._o = name, output
    def get_name(self): return self._n
    def get_output(self): return self._o


class _Method:
    def __init__(self, instrs): self._i = instrs
    def get_code(self): return object()
    def get_instructions(self): return self._i


class _Dex:
    def __init__(self, methods): self._m = methods
    def get_methods(self): return self._m
    def get_strings(self): return []          # for http_strings/all_urls


def _cs(frag): return _Ins("const-string", f"v3, '{frag}'")
def _inv(target): return _Ins("invoke-virtual", f"v0, {target}")


def dex_with(methods):
    d = analyseDEX.__new__(analyseDEX)
    d.dex = _Dex(methods)
    return d


def test_stringbuilder_host_plus_path():
    d = dex_with([_Method([
        _cs("https://api.deepseek.com"), _inv("Ljava/lang/StringBuilder;->append"),
        _cs("/v1/chat/completions"), _inv("Ljava/lang/StringBuilder;->append")])])
    assert "https://api.deepseek.com/v1/chat/completions" in d.find_built_urls()


def test_uri_builder_bare_host():
    d = dex_with([_Method([
        _cs("spclient.wg.spotify.com"), _inv("Landroid/net/Uri$Builder;->authority"),
        _cs("/melody/v1/msg"), _inv("Landroid/net/Uri$Builder;->appendPath")])])
    assert "https://spclient.wg.spotify.com/melody/v1/msg" in d.find_built_urls()


def test_retrofit_base_plus_relative():
    d = dex_with([_Method([
        _cs("https://api.plaud.ai/"), _inv("Lretrofit2/Retrofit$Builder;->baseUrl"),
        _cs("v1/transcribe/upload")])])
    assert "https://api.plaud.ai/v1/transcribe/upload" in d.find_built_urls()


def test_non_builder_method_does_not_stitch():
    """Two adjacent strings with no URL-builder invoke must NOT be joined
    into a fake URL."""
    d = dex_with([_Method([
        _cs("error_code"), _cs("hello.world"), _inv("Lcom/x/Logger;->log")])])
    assert all("hello.world" not in u for u in d.find_built_urls())


def test_whole_literal_still_found():
    d = dex_with([_Method([
        _cs("https://chat.deepseek.com/api/v0/session"),
        _inv("Ljava/lang/StringBuilder;->append")])])
    assert "https://chat.deepseek.com/api/v0/session" in d.find_built_urls()


def test_all_urls_unions_literals_and_built():
    class D2(_Dex):
        def get_strings(self):
            return ["https://literal.example.net/x"]
    d = analyseDEX.__new__(analyseDEX)
    d.dex = D2([_Method([
        _cs("https://built.example.net"),
        _inv("Ljava/lang/StringBuilder;->append"), _cs("/api")])])
    allu = set(d.all_urls())
    assert "https://literal.example.net/x" in allu        # from http_strings
    assert "https://built.example.net/api" in allu         # from find_built_urls
