"""
Unit testing localisation methods
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

def test_extract_language():
    mod = _import_or_skip(f"{PACKAGE}.localisation.localisation")
    loc = mod.Locales()
    assert loc.extract_language("values-es") == "es"

def test_extract_country():
    mod = _import_or_skip(f"{PACKAGE}.localisation.localisation")
    loc = mod.Locales()
    assert loc.extract_country("values-zh-rCN") == "CN"

def test_extract_device():
    mod = _import_or_skip(f"{PACKAGE}.localisation.localisation")
    loc = mod.Locales()
    assert loc.extract_device("values-zh-rCN-hdpi") == "hdpi"

def test_extract_device_long():
    mod = _import_or_skip(f"{PACKAGE}.localisation.localisation")
    loc = mod.Locales()
    assert loc.extract_device("values-zh-rCN-hdpi-night") == "hdpinight"