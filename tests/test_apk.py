"""
Unit testing apk methods
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
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    ap = mod.APK("filenm")
    assert ap.get_software_version("7.12.34") == 7.1234

@pytest.mark.skip(reason="waiting for mock to appear")
def test_apk_software_version():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    ap = mod.APK("filenm")
    assert ap.get_software_version("7.1234") == 7.1234

@pytest.mark.skip(reason="waiting for mock to appear")
def test_apk_software_version_dash():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    ap = mod.APK("filenm")
    assert ap.get_software_version("7.12.34_56") == 7.123456

def test_extract_language():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    loc = mod.APK("filenm")
    assert loc.extract_language("values-es") == "es"

def test_extract_country():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    loc = mod.APK("filenm")
    assert loc.extract_country("values-zh-rCN") == "CN"

def test_extract_device():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    loc = mod.APK("filenm")
    assert loc.extract_device("values-zh-rCN-hdpi") == "hdpi"

def test_extract_device_long():
    mod = _import_or_skip(f"{PACKAGE}.apk.apk")
    loc = mod.APK("filenm")
    assert loc.extract_device("values-zh-rCN-hdpi-night") == "hdpinight"