"""Tests for the StageProfiler harness."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.general.perf import StageProfiler, NullProfiler


def test_stages_aggregate_by_name():
    prof = StageProfiler(trace_python_memory=False)
    for _ in range(5):
        with prof.stage("work"):
            sum(range(10000))
    report = prof.report()
    assert len(report["stages"]) == 1
    s = report["stages"][0]
    assert s["stage"] == "work" and s["calls"] == 5
    assert s["wall_s"] >= s["wall_max_s"] >= 0


def test_nested_stage_labels():
    prof = StageProfiler(trace_python_memory=False)
    with prof.stage("outer"):
        with prof.stage("inner"):
            pass
    labels = {s["stage"] for s in prof.report()["stages"]}
    assert labels == {"outer", "outer.inner"}


def test_python_memory_tracked():
    prof = StageProfiler()
    with prof.stage("alloc"):
        block = bytearray(8 * 1024 * 1024)   # 8 MB
    report = prof.report()
    prof.close()
    s = report["stages"][0]
    assert s["py_kb_peak_max"] >= 8 * 1024
    del block


def test_report_is_json_serialisable_and_compact():
    prof = StageProfiler(trace_python_memory=False)
    for i in range(1000):                    # corpus-scale call counts...
        with prof.stage("per_file"):
            pass
    line = json.dumps(prof.report())
    assert len(line) < 2000                  # ...still one small JSON object


def test_null_profiler_is_inert():
    prof = NullProfiler()
    with prof.stage("anything"):
        x = 1
    assert prof.report() is None and prof.enabled is False
