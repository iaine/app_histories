"""
Stage profiler: timing and memory tracing for pipeline-shaped code.

Why not memory_profiler? Its line-by-line decorator model doesn't follow
class structures or call graphs well, and per-line sampling is the wrong
granularity for a corpus pipeline anyway. What you actually want to know
is "which *stage* (string extraction, classification, linking, ...) costs
what, summed over N files" -- so this harness profiles named stages:

    prof = StageProfiler()
    with prof.stage("extract_strings"):
        ...
    report = prof.report()      # JSON-safe dict, ready for the JSONL output

Measurements per stage:
  * wall_s        -- time.perf_counter (what the user waits for)
  * cpu_s         -- time.process_time (compute, excludes I/O waits)
  * py_kb_delta   -- Python-heap growth across the stage (tracemalloc)
  * py_kb_peak    -- Python-heap PEAK inside the stage (tracemalloc
                     reset_peak, so peaks are per-stage, not global)
  * rss_kb_delta  -- process RSS growth (captures native allocations
                     tracemalloc cannot see, e.g. inside lxml)

Stages are AGGREGATED by name (count / total / max), so a stage entered
once per file across a 10,000-APK shard yields one summary row, not
10,000 records -- the report stays JSONL-sized for HPC output.

Design notes:
  * NullProfiler is the default everywhere: a disabled profiler costs one
    attribute lookup and an if, so instrumentation can stay in production
    code paths.
  * tracemalloc tracks Python allocations only; RSS covers the rest.
    tracemalloc itself adds overhead (typically 1.5-3x slowdown and some
    memory): enable it for profiling runs, not production corpus runs,
    or construct StageProfiler(trace_python_memory=False) for timing+RSS
    only at near-zero overhead.
  * Caveat on nesting: tracemalloc has a single global peak counter, so
    a nested stage's reset_peak() truncates its parent's peak window.
    Wall/CPU/RSS/delta numbers nest correctly; treat py_kb_peak as
    reliable only for stages with no profiled children.
  * Complementary external tools (no code changes, good for validating
    this harness's numbers): py-spy record for sampled flamegraphs of a
    live run; memray run --native for allocation flamegraphs including
    native extensions; /usr/bin/time -v and SLURM's
    sacct --format=JobID,MaxRSS,Elapsed for whole-task ground truth.
"""

import contextlib
import os
import time
import tracemalloc

_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _rss_kb():
    """Current RSS in kB. Linux: /proc/self/statm (cheap, no psutil
    dependency). Elsewhere: returns 0 and RSS columns read as 0."""
    try:
        with open("/proc/self/statm") as fh:
            return int(fh.read().split()[1]) * _PAGE // 1024
    except (OSError, IndexError, ValueError):
        return 0


class NullProfiler:
    """Do-nothing stand-in so instrumented code needs no conditionals."""
    enabled = False

    @contextlib.contextmanager
    def stage(self, name):
        yield

    def report(self):
        return None


class StageProfiler:
    enabled = True

    def __init__(self, trace_python_memory=True):
        self.trace = trace_python_memory
        self._stack = []
        self._agg = {}          # label -> running stats
        self._t0 = time.perf_counter()
        self._owns_tracemalloc = False
        if self.trace and not tracemalloc.is_tracing():
            tracemalloc.start()
            self._owns_tracemalloc = True

    @contextlib.contextmanager
    def stage(self, name):
        label = ".".join(self._stack + [name])
        self._stack.append(name)

        if self.trace:
            tracemalloc.reset_peak()
            py0, _ = tracemalloc.get_traced_memory()
        rss0 = _rss_kb()
        w0, c0 = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            wall = time.perf_counter() - w0
            cpu = time.process_time() - c0
            rss_delta = _rss_kb() - rss0
            if self.trace:
                py1, py_peak = tracemalloc.get_traced_memory()
                py_delta = (py1 - py0) // 1024
                py_peak //= 1024
            else:
                py_delta = py_peak = 0

            s = self._agg.setdefault(label, {
                "calls": 0, "wall_s": 0.0, "wall_max_s": 0.0, "cpu_s": 0.0,
                "py_kb_delta": 0, "py_kb_peak_max": 0, "rss_kb_delta": 0,
            })
            s["calls"] += 1
            s["wall_s"] += wall
            s["wall_max_s"] = max(s["wall_max_s"], wall)
            s["cpu_s"] += cpu
            s["py_kb_delta"] += py_delta
            s["py_kb_peak_max"] = max(s["py_kb_peak_max"], py_peak)
            s["rss_kb_delta"] += rss_delta
            self._stack.pop()

    def wrap(self, name, func):
        """Decorator form: prof.wrap("classify", self.classify_so_pre)."""
        def wrapped(*args, **kwargs):
            with self.stage(name):
                return func(*args, **kwargs)
        return wrapped

    def report(self):
        """JSON-safe summary, stages sorted by total wall time."""
        stages = [
            dict(stage=label,
                 **{k: (round(v, 6) if isinstance(v, float) else v)
                    for k, v in stats.items()})
            for label, stats in self._agg.items()
        ]
        stages.sort(key=lambda s: -s["wall_s"])
        return {
            "total_wall_s": round(time.perf_counter() - self._t0, 6),
            "rss_kb_now": _rss_kb(),
            "python_memory_traced": self.trace,
            "stages": stages,
        }

    def close(self):
        if self._owns_tracemalloc and tracemalloc.is_tracing():
            tracemalloc.stop()
