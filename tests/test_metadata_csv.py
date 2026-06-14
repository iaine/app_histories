"""Tests for metadata CSV export (the flattener and writer)."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.metadata import (
    metadata_to_row, write_metadata_csv, CSV_COLUMNS, SENSITIVE_PERMISSIONS,
)


RECORD = {
    "pkg": "com.example.app", "applicationname": "Example",
    "android_name": "2.0", "version_code": "20",
    "permissions": "android.permission.RECORD_AUDIO;"
                   "android.permission.CAMERA;android.permission.INTERNET",
    "localisation": [["es", "", ""], ["zh", "rCN", ""], ["es", "", ""]],
    "ab": ["com.amplitude", "com.optimizely.ab"],
    "activities": "MainActivity;SettingsActivity",
}


def test_row_has_canonical_columns():
    row = metadata_to_row(RECORD)
    assert set(row) == set(CSV_COLUMNS)


def test_counts_and_sensitive_flagging():
    row = metadata_to_row(RECORD)
    assert row["permission_count"] == 3
    assert row["sensitive_permission_count"] == 2          # RECORD_AUDIO, CAMERA
    assert row["sensitive_permissions"] == "RECORD_AUDIO;CAMERA"
    assert "INTERNET" not in row["sensitive_permissions"]
    assert row["ab_sdk_count"] == 2 and row["activity_count"] == 2


def test_languages_deduped_and_sorted():
    row = metadata_to_row(RECORD)
    assert row["languages"] == "es;zh"                     # de-dup + sort


def test_handles_list_or_string_permission_fields():
    """metadata records may carry permissions as a ;-string or a list."""
    as_list = dict(RECORD, permissions=["android.permission.RECORD_AUDIO"])
    assert metadata_to_row(as_list)["permission_count"] == 1
    empty = dict(RECORD, permissions="", localisation=[], ab=[], activities="")
    row = metadata_to_row(empty)
    assert row["permission_count"] == 0 and row["language_count"] == 0


def test_full_cli_record_wrapper_is_flattened():
    """extract_metadata's dict may be wrapped with input/version/timestamp
    by the CLI; the flattener reads the same keys regardless."""
    wrapped = dict(RECORD, input="Example.apk", analysis="metadata",
                   toolkit_version="0.0.2")
    assert metadata_to_row(wrapped)["pkg"] == "com.example.app"


def test_write_csv_roundtrip_and_quoting(tmp_path):
    out = tmp_path / "corpus.csv"
    # second record has commas would-be-troublesome values
    other = dict(RECORD, pkg="com.b,inc", applicationname="B, Inc",
                 permissions="android.permission.INTERNET")
    write_metadata_csv([RECORD, other], out)

    rows = list(csv.DictReader(open(out, newline="")))
    assert [r["pkg"] for r in rows] == ["com.example.app", "com.b,inc"]
    assert rows[1]["applicationname"] == "B, Inc"          # comma survived
    assert list(rows[0].keys()) == CSV_COLUMNS


def test_sensitive_set_is_nonempty_contract():
    assert "RECORD_AUDIO" in SENSITIVE_PERMISSIONS
