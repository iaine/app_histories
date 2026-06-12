"""
Smoke tests for cim_app_histories.

Goal: prove that every module in the package can be imported, and that the
key public classes can be constructed and called with trivial inputs.
No APK files are required.

Run from the repository root with:

    pip install pytest
    pytest tests/test_smoke.py -v

Design notes
------------
* Modules are discovered automatically with pkgutil, so new modules are
  covered without editing this file.
* A missing *third-party* dependency (androguard, matplotlib, ...) is
  reported as a SKIP -- that is an environment problem, not a code problem.
* A SyntaxError, or an import of a module path that does not exist inside
  this repository (e.g. ``src.app_histories``), is reported as a FAIL --
  that is a code problem.
"""

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

# --- locate the package (src layout, works without `pip install -e .`) ----
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

PACKAGE = "cim_app_histories"

# Third-party distributions the code is known to use. If one of these is the
# thing that's missing, the environment is incomplete -> skip, don't fail.
THIRD_PARTY = {
    "androguard", "pandas", "matplotlib", "networkx",
    "numpy", "PIL", "loguru",
}


def discover_modules():
    """Yield every importable module name under the package directory."""
    pkg_dir = SRC / PACKAGE
    if not pkg_dir.is_dir():
        pytest.fail(f"Package directory not found: {pkg_dir}")
    # walk the filesystem rather than pkgutil.walk_packages(package) because
    # subpackages currently lack __init__.py and would be invisible to it.
    for py in sorted(pkg_dir.rglob("*.py")):
        rel = py.relative_to(SRC).with_suffix("")
        parts = rel.parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts)


MODULES = list(discover_modules())


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name):
    """Every module must at least import without error."""
    try:
        importlib.import_module(module_name)
    except SyntaxError as e:
        pytest.fail(f"SYNTAX ERROR in {module_name}: {e}")
    except ModuleNotFoundError as e:
        missing_root = (e.name or "").split(".")[0]
        if missing_root in THIRD_PARTY:
            pytest.skip(f"third-party dependency not installed: {e.name}")
        pytest.fail(
            f"BROKEN INTERNAL IMPORT in {module_name}: "
            f"no module named {e.name!r}"
        )
    except ImportError as e:
        pytest.fail(f"IMPORT ERROR in {module_name}: {e}")
    except Exception as e:  # import-time side effects (file I/O, plt.show...)
        pytest.fail(
            f"IMPORT-TIME SIDE EFFECT crashed in {module_name}: "
            f"{type(e).__name__}: {e}"
        )


# --------------------------------------------------------------------------
# Construction / trivial-call smoke tests for the documented public API.
# Each test imports lazily so an import failure shows up above, not here.
# --------------------------------------------------------------------------

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
def test_ab_class_constructs():
    """
    Test AB's move into dex(). 
    """
    mod = _import_or_skip(f"{PACKAGE}.dex.dex")
    ab = mod.DEX()
    assert isinstance(ab.AB_CLASSES, list) and len(ab.AB_CLASSES) > 0


def test_locales_constructs_and_extracts():
    """Locales() must construct from any CWD and parse a resource path."""
    mod = _import_or_skip(f"{PACKAGE}.localisation.localisation")
    loc = mod.Locales()
    assert loc.extract_language("values-es") == "es"
    assert loc.extract_country("values-zh-rCN") == "CN"


def test_classify_url_pure_functions():
    mod = _import_or_skip(f"{PACKAGE}.classify.classify_url")
    c = mod.ClassifyURL()
    assert c.generate_template("https://api.example.com/v1/user/123/x") == \
        "/v1/user/{id}/x"
    assert c.normalize_inputs(["audio", "bogus"]) == ["audio"]
    assert c.normalize_inputs([]) == ["other"]


def test_classify_so_pure_functions():
    mod = _import_or_skip(f"{PACKAGE}.classify.classify_so")
    c = mod.ClassifySO()
    # string extraction on a tiny synthetic binary
    strings = c.extract_strings(b"\x00\x01hello_model.tflite\x00\xff")
    assert any("tflite" in s for s in strings)
    # entropy on trivial data must not divide by zero or hang
    assert c.entropy(b"aaaabbbb") == pytest.approx(1.0)
    # vendor detection from a string *list* (regression guard for the
    # join-of-a-string bug: passing data through detect_vendor must still
    # find the vendor named in the global strings)
    v = c.detect_vendor("mystery.bin", ["uses tencent tnn runtime"])
    assert v == "tencent"


def test_exception_class_raisable():
    mod = _import_or_skip(f"{PACKAGE}.general.exception")
    with pytest.raises(mod.CastException):
        raise mod.CastException("boom", errors=["e1"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
