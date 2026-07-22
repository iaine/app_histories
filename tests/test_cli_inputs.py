"""
Tests for CLI corpus-directory input: deterministic collection,
shard partitioning, and collision-proof output naming.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.cli import collect_inputs, make_output_names, shard


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "apps"
    (d / "sub").mkdir(parents=True)
    for i in range(25):
        (d / f"app_{i:02d}.apk").write_bytes(b"PK")
    (d / "duplicate.apk").write_bytes(b"PK")
    (d / "sub" / "duplicate.apk").write_bytes(b"PK")
    (d / "notes.txt").write_bytes(b"x")
    (d / ".hidden.apk").write_bytes(b"PK")
    (d / "UPPER.APK").write_bytes(b"PK")
    return d


def test_collect_filters_and_sorts(corpus):
    paths = collect_inputs(None, None, str(corpus))
    names = [p.name for p in paths]
    assert names == sorted(names)               # deterministic order
    assert "notes.txt" not in names             # non-apk excluded
    assert ".hidden.apk" not in names           # hidden excluded
    assert "UPPER.APK" in names                 # case-insensitive suffix
    assert "duplicate.apk" in names
    assert len([n for n in names if n == "duplicate.apk"]) == 1  # no recurse


def test_collect_recursive_includes_subdirs(corpus):
    paths = collect_inputs(None, None, str(corpus), recursive=True)
    dups = [p for p in paths if p.name == "duplicate.apk"]
    assert len(dups) == 2


def test_collect_rejects_non_directory(tmp_path):
    with pytest.raises(SystemExit):
        collect_inputs(None, None, str(tmp_path / "missing"))


def test_sharding_partitions_exactly(corpus):
    """Union of all shards == full list, with no overlaps: the property
    that lets independent SLURM array tasks divide a directory safely."""
    inputs = collect_inputs(None, None, str(corpus), recursive=True)
    for task_count in (1, 3, 8, len(inputs) + 5):
        shards = [shard(inputs, i, task_count) for i in range(task_count)]
        union = [p for s in shards for p in s]
        assert sorted(union) == sorted(inputs)
        assert len(union) == len(set(union))


def test_output_names_collide_proof_and_deterministic(corpus):
    inputs = collect_inputs(None, None, str(corpus), recursive=True)
    names = make_output_names(inputs, "metadata")
    assert len(set(names.values())) == len(inputs)        # all distinct
    dup_names = {v for k, v in names.items() if k.stem == "duplicate"}
    assert len(dup_names) == 2
    assert all(len(n.split(".")) == 4 for n in dup_names)  # hash inserted
    unique = [v for k, v in names.items() if k.stem == "app_00"]
    assert unique == ["app_00.metadata.jsonl"]             # plain when unique
    assert names == make_output_names(list(inputs), "metadata")  # stable


def test_apk_dir_accepts_bundles_and_skips_split_members(tmp_path):
    """--apk-dir must find .xapk/.apks/.apkm bundles, and must NOT list a
    loose split as its own app: collect_all_files merges splits into the
    base, so listing one separately would analyse a fragment and
    double-count."""
    from cim_app_histories.cli import collect_inputs
    for n in ["app.apk", "bundle.xapk", "other.apks", "third.apkm",
              "config.arm64_v8a.apk", "split_config.x86.apk"]:
        (tmp_path / n).write_bytes(b"x")
    found = [p.name for p in collect_inputs(None, None, str(tmp_path), False)]
    assert "app.apk" in found
    assert "bundle.xapk" in found
    assert "other.apks" in found and "third.apkm" in found
    assert "config.arm64_v8a.apk" not in found
    assert "split_config.x86.apk" not in found
