"""Bundle (XAPK/APKS/APKM) ingestion tests."""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.bundle import (          # noqa: E402
    classify_split, select_members, is_bundle, open_bundle)


def test_classify_split_decodes_every_kind():
    """The 'x' in config.x.apk drives both selection and provenance, so
    each kind must decode correctly across all three bundle formats'
    naming conventions."""
    cases = [
        ("base.apk", "base"),
        ("base-master.apk", "base"),
        ("config.arm64_v8a.apk", "abi"),
        ("config.armeabi_v7a.apk", "abi"),
        ("config.x86_64.apk", "abi"),
        ("split_config.arm64_v8a.apk", "abi"),     # APKM style
        ("base-arm64_v8a.apk", "abi"),             # bundletool style
        ("config.en.apk", "language"),
        ("config.zh.apk", "language"),
        ("base-fr.apk", "language"),
        ("config.xxhdpi.apk", "density"),
        ("split_dynamic_feature.apk", "feature"),
    ]
    for name, expected in cases:
        assert classify_split(name)["kind"] == expected, name


def test_abi_value_is_normalised():
    """ABI values use Android's hyphenated form so they match lib paths."""
    assert classify_split("config.arm64_v8a.apk")["value"] == "arm64-v8a"


def test_select_prefers_arm64_and_skips_density():
    """Merging every ABI would count each library once per architecture.
    Take one (arm64 first); density splits carry resources, not code."""
    members = {n: classify_split(n) for n in [
        "base.apk", "config.arm64_v8a.apk", "config.armeabi_v7a.apk",
        "config.x86_64.apk", "config.xxhdpi.apk", "config.en.apk"]}
    chosen, abis = select_members(members)
    assert "config.arm64_v8a.apk" in chosen
    assert "config.armeabi_v7a.apk" not in chosen
    assert "config.x86_64.apk" not in chosen
    assert "config.xxhdpi.apk" not in chosen      # density skipped
    assert "config.en.apk" in chosen              # languages always kept
    assert set(abis) == {"arm64-v8a", "armeabi-v7a", "x86_64"}


def test_select_all_abis_when_requested():
    """A study comparing architectures can opt into the duplication."""
    members = {n: classify_split(n) for n in [
        "base.apk", "config.arm64_v8a.apk", "config.x86_64.apk"]}
    chosen, _ = select_members(members, abi_policy="all")
    assert "config.arm64_v8a.apk" in chosen and "config.x86_64.apk" in chosen


def test_select_falls_back_when_no_preferred_abi():
    """Only an unusual ABI present: take it rather than returning nothing."""
    members = {n: classify_split(n) for n in ["base.apk", "config.mips.apk"]}
    chosen, _ = select_members(members)
    assert "config.mips.apk" in chosen


def _make_bundle(tmp_path, name="app.xapk", manifest=True):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("base.apk", b"PK\x03\x04stub")
        z.writestr("config.arm64_v8a.apk", b"PK\x03\x04stub")
        z.writestr("config.en.apk", b"PK\x03\x04stub")
        z.writestr("icon.png", b"\x89PNG")
        if manifest:
            z.writestr("manifest.json", json.dumps(
                {"package_name": "com.demo", "version_name": "1.2"}))
    return p


def test_is_bundle_detects_by_extension_and_content(tmp_path):
    b = _make_bundle(tmp_path)
    assert is_bundle(b)
    plain = tmp_path / "plain.txt"
    plain.write_text("not a zip")
    assert not is_bundle(plain)


def test_open_bundle_extracts_and_records_provenance(tmp_path):
    """Provenance is research data: which ABI was read makes the analysis
    reproducible, and the language list is a localisation signal."""
    b = _make_bundle(tmp_path)
    dest = tmp_path / "out"
    paths, meta = open_bundle(b, dest)
    names = [p.name for p in paths]
    assert names[0] == "base.apk", "base must be first so its classes win"
    assert "config.arm64_v8a.apk" in names
    assert "icon.png" not in names               # non-APK members skipped
    assert meta["format"] == "xapk"
    assert meta["abi_used"] == "arm64-v8a"
    assert meta["languages"] == ["en"]
    assert meta["package_name"] == "com.demo"


def test_open_bundle_without_manifest_falls_back_to_filenames(tmp_path):
    """The manifest is a convenience, not a dependency."""
    b = _make_bundle(tmp_path, manifest=False)
    paths, meta = open_bundle(b, tmp_path / "out2")
    assert [p.name for p in paths][0] == "base.apk"
    assert meta["abi_used"] == "arm64-v8a"
    assert "package_name" not in meta


def test_apkpure_style_base_named_after_package(tmp_path):
    """APKPure names the base after the package rather than 'base.apk'
    (the real Live Transcribe bundle does this), so the unknown member
    must be promoted to base or nothing is analysed."""
    p = tmp_path / "lt.xapk"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("com.google.audio.scribe.apk", b"PK\x03\x04stub")
        z.writestr("config.arm64_v8a.apk", b"PK\x03\x04stub")
    paths, meta = open_bundle(p, tmp_path / "out3")
    assert [x.name for x in paths][0] == "com.google.audio.scribe.apk"
    assert meta["abi_used"] == "arm64-v8a"
