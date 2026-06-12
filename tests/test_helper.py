"""
Regression tests for Helper.list_similarity.

This function diffs item lists across successive app versions (the core
"app histories" operation: which SDKs appeared/disappeared between
releases). The upstream implementation silently produced garbage --
it diffed the *characters of the version label* and computed "added"
and "removed" as the same intersection -- so these tests pin the
correct semantics: added = new - old, removed = old - new.

Run with: pytest tests/test_helpers.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.general.helpers import Helper


@pytest.fixture
def helper():
    return Helper()


def test_basic_add_and_remove(helper):
    """The motivating case: one SDK dropped, one adopted between versions."""
    history = {
        "v1.0": ["com.abtasty", "io.adapty"],
        "v2.0": ["com.abtasty", "com.amplitude"],
    }
    changes = helper.list_similarity(history)

    assert changes["v1.0"] == {"added": ["com.abtasty", "io.adapty"],
                               "removed": []}
    assert changes["v2.0"] == {"added": ["com.amplitude"],
                               "removed": ["io.adapty"]}


def test_added_and_removed_are_not_symmetric(helper):
    """Direct regression guard for the swapped-intersection bug: when the
    change is one-directional, exactly one of the sets must be empty."""
    changes = helper.list_similarity({
        "v1": ["a", "b"],
        "v2": ["a", "b", "c"],   # pure addition
        "v3": ["a"],             # pure removal
    })
    assert changes["v2"] == {"added": ["c"], "removed": []}
    assert changes["v3"] == {"added": [], "removed": ["b", "c"]}


def test_items_diffed_not_version_labels(helper):
    """Regression guard for the set(test)-of-characters bug: version
    labels sharing characters must contribute nothing to the diff."""
    changes = helper.list_similarity({
        "v1.0": ["sdk.one"],
        "v2.0": ["sdk.one"],     # identical lists, similar labels
    })
    assert changes["v2.0"] == {"added": [], "removed": []}
    # The upstream code reported {'.', '0', 'v'} as both added and removed.
    for version in changes.values():
        for value in version.values():
            assert "v" not in value and "." not in value


def test_no_change_between_versions(helper):
    changes = helper.list_similarity({
        "v1": ["x", "y"],
        "v2": ["y", "x"],        # same set, different order
    })
    assert changes["v2"] == {"added": [], "removed": []}


def test_empty_middle_version(helper):
    """A version with zero SDKs is a real observation, not a reset:
    the next version must diff against it, not be treated as 'first'."""
    changes = helper.list_similarity({
        "v1": ["a"],
        "v2": [],
        "v3": ["a", "b"],
    })
    assert changes["v2"] == {"added": [], "removed": ["a"]}
    assert changes["v3"] == {"added": ["a", "b"], "removed": []}


def test_duplicates_within_a_version_collapse(helper):
    """Set semantics: a signature matched twice in one version is one item."""
    changes = helper.list_similarity({
        "v1": ["a", "a", "b"],
        "v2": ["b"],
    })
    assert changes["v1"] == {"added": ["a", "b"], "removed": []}
    assert changes["v2"] == {"added": [], "removed": ["a"]}


def test_output_is_deterministic(helper):
    """Sorted lists, not sets: stable across runs for diffable outputs."""
    history = {"v1": ["z", "m", "a"], "v2": []}
    changes = helper.list_similarity(history)
    assert changes["v1"]["added"] == ["a", "m", "z"]
    assert changes["v2"]["removed"] == ["a", "m", "z"]


def test_single_and_empty_inputs(helper):
    assert helper.list_similarity({}) == {}
    assert helper.list_similarity({"v1": []}) == {
        "v1": {"added": [], "removed": []}
    }