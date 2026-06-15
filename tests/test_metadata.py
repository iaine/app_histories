"""
Tests for the metadata workflow and the AB/localisation logic rolled
into analyseDEX and extractAPK. Uses lightweight fakes so no real APK
is needed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.apk.apk import extractAPK
from cim_app_histories.dex.dex import analyseDEX


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------
class FakeClass:
    def __init__(self, descriptor):
        self._d = descriptor

    def get_name(self):
        return self._d


class FakeDex:
    def __init__(self, descriptors):
        self._classes = [FakeClass(d) for d in descriptors]

    def get_classes(self):
        return self._classes


def dex_with(descriptors):
    d = analyseDEX.__new__(analyseDEX)      # skip DEX() construction
    d.dex = FakeDex(descriptors)
    return d


class FakeAPK:
    """Stands in for androguard's APK (assigned to extractAPK.apk), so it
    exposes get_files() returning raw archive paths. extractAPK.get_locales()
    processes those paths into (language, region, device) tuples."""
    def __init__(self, files):
        self._files = files

    def get_files(self):
        return self._files


def apk_with(files):
    a = extractAPK.__new__(extractAPK)      # skip androguard construction
    a.apk = FakeAPK(files)
    return a


# ---------------------------------------------------------------------------
# A/B detection (now in analyseDEX)
# ---------------------------------------------------------------------------
def test_ab_matches_dex_format_class_names():
    """DEX stores Lcom/abtasty/Foo; -- the detector must match dotted
    signatures against that (the previous comparison never could)."""
    d = dex_with(["Lcom/abtasty/Core;", "Lio/adapty/Adapty;",
                  "Lcom/example/app/Main;"])
    assert d.find_ab_by_package() == ["com.abtasty", "io.adapty"]


def test_ab_matching_is_anchored_not_substring():
    """io.split must not match studio.splitties; com.batch.android must
    not match com.batchmate.other."""
    d = dex_with(["Lstudio/splitties/views/View;",
                  "Lcom/batchmate/other/Thing;"])
    assert d.find_ab_by_package() == []


def test_ab_exact_class_and_subpackage_both_match():
    d = dex_with(["Lcom/optimizely/ab;"])
    assert d.find_ab_by_package() == ["com.optimizely.ab"]
    d = dex_with(["Lcom/optimizely/ab/config/Config;"])
    assert d.find_ab_by_package() == ["com.optimizely.ab"]


# ---------------------------------------------------------------------------
# localisation (now in extractAPK)
# ---------------------------------------------------------------------------
def test_locale_parsing_from_resource_paths():
    a = apk_with([
        "res/values-es/strings.xml",
        "res/values-zh-rCN/strings.xml",
        "res/values-b+es+419/strings.xml",
        "res/values-fr-sw600dp/strings.xml",   # device qualifier, not region
        "res/values/strings.xml",              # default locale: skipped
        "res/mipmap-anydpi-v26/icon.xml",      # not a language
        "classes.dex",
    ])
    locales = a.get_locales()
    assert ("zh", "CN", "") in locales
    assert ("es", "", "") in locales
    assert ("es", "419", "") in locales
    assert ("fr", "", "") in locales
    langs = {l for l, _, _ in locales}
    assert "anydpi" not in langs and "" not in langs


def test_locale_full_path_not_split_as_language():
    """Regression guard: splitting the full path on '-' returned
    'es/strings.xml' as a language."""
    a = apk_with(["res/values-es/strings.xml"])
    for lang, _, _ in a.get_locales():
        assert "/" not in lang


def test_locale_results_deduplicated():
    a = apk_with(["res/values-de/strings.xml",
                  "res/values-de/colors.xml",
                  "res/values-de/dimens.xml"])
    assert a.get_locales() == [("de", "", "")]


def test_extract_country_validates_regions():
    a = apk_with([])
    assert a.extract_country("values-zh-rCN") == "CN"
    assert a.extract_country("values-b+es+419") == "419"
    assert a.extract_country("values-fr-sw600dp") == ""
    assert a.extract_country("values-sr-rLatn") == ""


# ---------------------------------------------------------------------------
# the workflow record (extractAPK/analyseDEX faked at module seams)
# ---------------------------------------------------------------------------
def test_extract_metadata_record(monkeypatch):
    from cim_app_histories.calls import metadata as md

    class FakeExtract:
        def __init__(self, apkname):
            self.apk = self
        def applicationname(self): return "Demo"
        def packagename(self): return "com.example.demo"
        def android_version_code(self): return "42"
        def android_version_name(self): return "1.2.3"
        def permissions(self): return "android.permission.CAMERA"
        def activities(self): return "com.example.Main"
        def get_locales(self): return [("es", "", "")]
        def get_all_dex(self):           # two dex files: multidex merge
            yield b"dex1"; yield b"dex2"

    class FakeAnalyse:
        def __init__(self, buff): self._buff = buff
        def find_ab_by_package(self):
            return ["com.abtasty"] if self._buff == b"dex1" else ["io.adapty"]
        def find_trackers(self):
            return ([{"signature": "com.adjust.sdk", "name": "Adjust",
                      "category": "analytics"}] if self._buff == b"dex1" else [])

    monkeypatch.setattr(md, "extractAPK", FakeExtract)
    monkeypatch.setattr(md, "analyseDEX", FakeAnalyse)

    rec = md.extract_metadata("demo.apk")
    assert rec["pkg"] == "com.example.demo"
    assert rec["localisation"] == [("es", "", "")]
    assert rec["ab"] == ["com.abtasty", "io.adapty"]   # merged across dexes
    assert [t["signature"] for t in rec["trackers"]] == ["com.adjust.sdk"]


def test_cli_has_metadata_and_not_ab_localisation():
    from cim_app_histories.cli import TASKS
    assert "metadata" in TASKS
    assert "ab" not in TASKS and "localisation" not in TASKS


# --- locales from resources.arsc (the TikTok empty-localisation fix) -------
def test_locales_read_from_arsc_when_no_res_paths():
    """Modern APKs compile res/values-*/ into resources.arsc and list no
    res/values-* file entries; locales must come from the arsc."""
    from cim_app_histories.apk.apk import extractAPK

    class FakeARSC:
        def get_packages_names(self): return ["com.app"]
        def get_locales(self, pkg):
            return ["", "en", "en-US", "zh-CN", "b+es+419", "de-rDE"]

    class ArscAPK:
        def get_android_resources(self): return FakeARSC()
        def get_files(self): return ["resources.arsc", "classes.dex"]

    a = extractAPK.__new__(extractAPK); a.apk = ArscAPK()
    locs = a.get_locales()
    assert ("zh", "CN", "") in locs
    assert ("en", "US", "") in locs
    assert ("es", "419", "") in locs        # BCP-47 numeric region
    assert ("de", "DE", "") in locs         # legacy -rDE form
    assert all(l for l, _, _ in locs)       # no empty/default language


def test_locales_fallback_to_paths_without_arsc():
    from cim_app_histories.apk.apk import extractAPK

    class NoArscAPK:
        def get_android_resources(self): return None
        def get_files(self): return ["res/values-pt/strings.xml"]

    a = extractAPK.__new__(extractAPK); a.apk = NoArscAPK()
    assert ("pt", "", "") in a.get_locales()


def test_metadata_record_has_no_intents():
    """intents was removed from the metadata record."""
    import inspect
    from cim_app_histories.calls import metadata as md
    assert "intents" not in inspect.getsource(md.extract_metadata)
