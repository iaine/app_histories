# Profiling: timing and memory tracing

The toolkit includes a stage profiler (`cim_app_histories.general.perf`)
for measuring where pipeline runs spend time and memory. This page
explains why it works the way it does, how to use it from the CLI and
from code, how to read its numbers, and when to reach for external
tools instead.

## Why stage profiling rather than line profiling

Line-oriented tools such as `memory_profiler` decorate individual
functions and report per-line costs. That model fights class-structured
code (every method needs decorating, inheritance and callbacks confuse
attribution) and is the wrong granularity for a corpus pipeline anyway:
the question is not "which line allocates" but "what does each *stage*
— string extraction, classification, link building — cost, summed over
ten thousand APKs".

The harness therefore profiles named stages. You place the boundaries
with a context manager, so it follows any code structure, and results
are aggregated by stage name: a stage entered once per file across a
whole shard produces one summary row (count, total, max), keeping the
report at JSON-line size no matter how large the corpus.

## Quick start

From the CLI, add `--profile` to a `flows` run:

```bash
cim-apps flows --apk app.apk --outdir results/ --profile
```

Each output record in `results/<app>.flows.jsonl` gains a `"profile"`
section. On a SLURM array this means per-stage economics for every app
in the corpus, embedded in the data you were already collecting:

```bash
#SBATCH --array=0-99
apptainer run cim-apps.sif flows \
    --apk-list corpus.txt --outdir results/ --profile \
    --task-index "$SLURM_ARRAY_TASK_ID" --task-count 100
```

From code:

```python
from cim_app_histories.general.perf import StageProfiler
from cim_app_histories.calls.multimodal_pipeline import build_flow_graph

prof = StageProfiler()
graph = build_flow_graph(files, permissions=perms, profiler=prof)
report = prof.report()
prof.close()
```

To instrument your own code, wrap the phases that matter:

```python
prof = StageProfiler()
for name, data in files:
    with prof.stage("extract"):
        strings = extract(data)
    with prof.stage("classify"):
        result = classify(name, strings)
print(prof.report())
```

Stages nest, producing dotted labels (`outer.inner`). A decorator form
exists for wrapping existing callables without editing them:
`classify = prof.wrap("classify", classifier.classify_so_pre)`.

## Reading the report

```json
{"total_wall_s": 4.36, "rss_kb_now": 95436, "python_memory_traced": true,
 "stages": [
   {"stage": "classify_module", "calls": 30, "wall_s": 1.504,
    "wall_max_s": 0.089, "cpu_s": 1.489, "py_kb_delta": 0,
    "py_kb_peak_max": 63753, "rss_kb_delta": 61552}, ...]}
```

| Field | Meaning |
|---|---|
| `calls` | times the stage was entered (aggregated by name) |
| `wall_s` / `wall_max_s` | total and worst-case elapsed time — what a user or job waits for |
| `cpu_s` | process CPU time; a large wall−cpu gap means waiting (I/O, locks), not computing |
| `py_kb_delta` | net Python-heap growth across all calls; persistent growth here suggests retained objects |
| `py_kb_peak_max` | highest Python-heap high-water mark observed during any single call |
| `rss_kb_delta` | net process RSS growth; this is what the OS and SLURM see, and includes native allocations invisible to tracemalloc |

Two readings worth internalising. A stage with large `py_kb_peak_max`
but near-zero `py_kb_delta` allocates transiently and cleans up — the
peak tells you the memory headroom one worker needs. A stage where
`rss_kb_delta` grows but `py_kb_delta` does not points at native-code
allocations (or allocator fragmentation), which is your cue for memray
(below).

Per-app reports across a corpus analyse naturally with pandas:

```python
import json, pandas as pd, pathlib
rows = [{"app": r["input"], **s}
        for p in pathlib.Path("results").glob("*.flows.jsonl")
        for r in map(json.loads, open(p))
        for s in r.get("profile", {}).get("stages", [])]
df = pd.DataFrame(rows)
print(df.groupby("stage")[["wall_s", "py_kb_peak_max"]]
        .agg({"wall_s": "sum", "py_kb_peak_max": "max"})
        .sort_values("wall_s", ascending=False))
```

## Costs and caveats

The profiler is honest about its own overhead. Python-memory tracing
uses `tracemalloc`, which typically slows execution 1.5–3x and adds
memory of its own; it is therefore opt-in. For timing and RSS only, at
near-zero overhead, construct `StageProfiler(trace_python_memory=False)`.
Library code instrumented with stages defaults to `NullProfiler`, a
do-nothing stand-in, so unprofiled production runs are unaffected — the
test suite asserts that profiled and unprofiled runs produce identical
results.

Three measurement caveats. First, `tracemalloc` sees Python allocations
only; native allocations show up solely in the RSS columns. Second, the
peak counter is process-global: a nested stage's reset truncates its
parent's peak window, so treat `py_kb_peak_max` as reliable for stages
with no profiled children (timings and deltas nest correctly). Third,
RSS is read from `/proc/self/statm`, so RSS columns are zero on
non-Linux platforms; everything else works everywhere.

## When to use external tools instead

The harness gives continuous, corpus-scale numbers embedded in your
output data. For occasional deep dives, three external tools complement
it without code changes. `py-spy` produces sampled flamegraphs of a live
process and can attach to a running HPC task by PID
(`py-spy record -o flame.svg --pid <pid>` or
`py-spy record -- cim-apps flows ...`), at negligible overhead. `memray`
(`memray run --native -o out.bin cim-apps flows ...`, then
`memray flamegraph out.bin`) produces allocation flamegraphs that *do*
include native extensions — the strongest tool whenever RSS and
tracemalloc disagree. `Scalene` offers line-level profiles separating
Python, native, and copy costs, useful on a laptop once the harness has
told you which stage to stare at. For whole-job ground truth on the
cluster, `/usr/bin/time -v` reports peak RSS for any command, and
`sacct --format=JobID,MaxRSS,Elapsed` reports what SLURM actually
charged you; the harness's numbers should reconcile with both.

