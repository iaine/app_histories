"""ACR (automatic content recognition) detection tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.acr import acr   # noqa: E402


# --- data files load -------------------------------------------------
def test_seed_vocabularies_load():
    sdks = acr.load_sdks()
    sigs = acr.load_signatures()
    assert any(r["vendor"] == "ACRCloud" for r in sdks)
    assert sigs["native"] and sigs["path"] and sigs["keyword"]


# --- SDK package detection (anchored, like trackers) -----------------
def test_find_acr_sdks_matches_named_vendor():
    hits = acr.find_acr_sdks(["Lcom/acrcloud/rec/ACRCloudClient;",
                              "Lcom/example/App;"])
    assert [h["vendor"] for h in hits] == ["ACRCloud"]


def test_find_acr_sdks_rejects_lookalike():
    """com.acrcloudy must not match com.acrcloud (anchored prefix)."""
    assert acr.find_acr_sdks(["Lcom/acrcloudy/Fake;"]) == []


# --- native library detection ----------------------------------------
def test_find_acr_native_matches_fingerprint_lib():
    """QQ Music ships libfingerprint_jni.so -- the generic seed catches it."""
    hits = acr.find_acr_native(["lib/arm64/libfingerprint_jni.so",
                                "lib/arm64/libc++_shared.so"])
    assert any(h["library"] == "libfingerprint_jni.so" for h in hits)


def test_find_acr_native_matches_netease_confirmed_lib():
    hits = acr.find_acr_native(
        ["lib/arm64/libNeSRAudioRecAndFpExtractor.so"])
    assert any(h["vendor"] == "NetEase" for h in hits)


def test_find_acr_native_ignores_benign_lib():
    assert acr.find_acr_native(["lib/arm64/libaudio.so"]) == []


# --- endpoint detection ----------------------------------------------
def test_find_acr_endpoints_matches_recognition_paths():
    urls = ["https://identify-eu.acrcloud.com/v1/identify",
            "https://cdn.example.com/image.png"]
    hits = acr.find_acr_endpoints(urls)
    assert any("acrcloud" in h["url"] for h in hits)


# --- CJK keyword detection (corroboration only) ----------------------
def test_find_acr_keywords_matches_confirmed_phrase():
    hits = acr.find_acr_keywords(["听歌识曲结果", "unrelated"])
    assert any(h["keyword"] == "听歌识曲" for h in hits)


def test_find_acr_keywords_rejects_innocent_compound():
    """知识曲库 ('knowledge song library') must not match: 识 and 曲 come
    from different words. Only anchored phrases are in the table."""
    assert acr.find_acr_keywords(["知识曲库", "认识曲作者"]) == []


# --- confidence grading ----------------------------------------------
def test_grade_named_sdk_is_high():
    assert acr.grade_confidence(True, [], [], False, []) == "high"


def test_grade_multiple_fingerprint_libs_is_high():
    """NetEase ships three fp libs and no named SDK -- still high."""
    native = [{"library": "a"}, {"library": "b"}, {"library": "c"}]
    assert acr.grade_confidence(False, native, [], True, []) == "high"


def test_grade_one_lib_plus_capture_is_medium():
    assert acr.grade_confidence(
        False, [{"library": "a"}], [], True, []) == "medium"


def test_grade_capture_only_is_low():
    assert acr.grade_confidence(False, [], [], True, []) == "low"


def test_grade_keyword_alone_is_none():
    """The 畅听音乐 case: a 听歌识曲 *chart label* with no capture, no lib,
    no SDK must grade none -- the keyword is inert without a primary
    signal, which is what stops a plain music player being flagged."""
    assert acr.grade_confidence(
        False, [], [], False, [{"keyword": "听歌识曲"}]) == "none"
