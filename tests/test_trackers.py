"""
Tests for analyseDEX.find_trackers and the packaged tracker data, plus
the tracker columns in the metadata CSV.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.dex.dex import analyseDEX
from cim_app_histories.calls.metadata import metadata_to_row, CSV_COLUMNS


# ---- fakes (skip DEX() construction) ---------------------------------
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
    d = analyseDEX.__new__(analyseDEX)
    d.dex = FakeDex(descriptors)
    return d


# ---- the data file ---------------------------------------------------
def test_tracker_table_loads_and_is_well_formed():
    trackers = analyseDEX.trackers()
    assert len(trackers) > 40
    for t in trackers:
        assert t["signature"] and t["name"] and t["category"]
        assert " " not in t["signature"]           # no stray whitespace


def test_tracker_table_is_cached():
    assert analyseDEX.trackers() is analyseDEX.trackers()


# ---- detection -------------------------------------------------------
def test_find_trackers_matches_packaged_signatures():
    d = dex_with(["Lcom/google/firebase/analytics/FirebaseAnalytics;",
                  "Lcom/adjust/sdk/Adjust;",
                  "Lcom/example/app/Main;"])
    found = {t["signature"] for t in d.find_trackers()}
    assert "com.google.firebase.analytics" in found
    assert "com.adjust.sdk" in found
    assert len(found) == 2


def test_find_trackers_returns_category():
    d = dex_with(["Lcom/google/android/gms/ads/AdView;"])
    hit = d.find_trackers()
    assert hit and hit[0]["category"] == "advertising"


def test_find_trackers_anchored_not_substring():
    """A class merely containing a signature as a substring must not
    match; only equality or a subpackage does."""
    d = dex_with(["Lcom/adjustment/tool/Thing;",      # not com.adjust.sdk
                  "Lcom/myinmob/x/Y;"])                # not com.inmobi
    assert d.find_trackers() == []


def test_find_trackers_empty_when_none_present():
    d = dex_with(["Lcom/example/app/Main;", "Landroidx/core/View;"])
    assert d.find_trackers() == []


# ---- metadata CSV integration ---------------------------------------
def test_csv_has_tracker_columns():
    assert "tracker_count" in CSV_COLUMNS
    assert "trackers" in CSV_COLUMNS
    assert "tracker_categories" in CSV_COLUMNS


def test_csv_flattens_tracker_descriptors():
    rec = {
        "pkg": "com.x", "permissions": "", "localisation": [], "ab": [],
        "activities": "",
        "trackers": [
            {"signature": "com.adjust.sdk", "name": "Adjust",
             "category": "analytics"},
            {"signature": "com.google.android.gms.ads", "name": "Google AdMob",
             "category": "advertising"},
        ],
    }
    row = metadata_to_row(rec)
    assert row["tracker_count"] == 2
    assert row["trackers"] == "Adjust;Google AdMob"
    assert row["tracker_categories"] == "advertising;analytics"  # sorted, unique


def test_csv_tolerates_bare_signature_strings():
    rec = {"pkg": "com.x", "permissions": "", "localisation": [], "ab": [],
           "activities": "", "trackers": ["com.flurry.android"]}
    row = metadata_to_row(rec)
    assert row["tracker_count"] == 1
    assert row["trackers"] == "com.flurry.android"
