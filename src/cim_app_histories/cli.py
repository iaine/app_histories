"""
cim-apps: command-line interface for the CIM App Histories toolkit.

Designed so the *same command* runs on a laptop and on an HPC cluster:

* one invocation processes one APK or a shard of a list;
* results are JSON-Lines, one record per finding, written atomically
  (temp file + rename), so a killed job never leaves a truncated file;
* completed outputs are skipped on re-run, so a resubmitted SLURM
  array heals partial failures;
* worker count respects the CPUs actually allocated to the job
  (cgroup/SLURM affinity), not the machine's nominal core count.

Laptop:
    cim-apps classify --apk app.apk --outdir results/
    cim-apps metadata --apk app.apk --outdir results/

Directory of apps (the common case: a scraped corpus folder):
    cim-apps metadata --apk-dir apps/ --outdir results/

HPC (SLURM array over a corpus, one shard per array task):
    cim-apps classify --apk-dir /scratch/apps --outdir results/ \\
        --task-index "$SLURM_ARRAY_TASK_ID" --task-count "$SLURM_ARRAY_TASK_COUNT"
"""

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import metadata
from pathlib import Path


# ----------------------------------------------------------------------
# infrastructure
# ----------------------------------------------------------------------

def default_workers():
    """CPUs actually available to this process (respects SLURM/cgroups)."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:          # non-Linux laptop
        return os.cpu_count() or 1


def shard(items, task_index, task_count):
    """Deterministic round-robin shard for array jobs."""
    if task_count <= 1:
        return list(items)
    return [x for i, x in enumerate(items) if i % task_count == task_index]


def collect_inputs(single, list_file, directory=None, recursive=False):
    if single:
        return [Path(single)]
    if list_file:
        return [Path(line.strip())
                for line in Path(list_file).read_text().splitlines()
                if line.strip() and not line.startswith("#")]

    base = Path(directory)
    if not base.is_dir():
        raise SystemExit(f"--apk-dir is not a directory: {base}")
    walk = base.rglob("*") if recursive else base.iterdir()
    # sorted() is load-bearing: every SLURM array task scans the
    # directory independently, so all tasks must derive the IDENTICAL
    # ordered list for round-robin sharding to partition cleanly.
    return sorted(
        p for p in walk
        if p.is_file() and p.suffix.lower() == ".apk"
        and not p.name.startswith(".")
    )


# Workflows whose output is one pretty-printed .json object per app
# rather than JSON-Lines.
JSON_OBJECT_WORKFLOWS = {"listening"}


def make_output_names(inputs, kind):
    """Output filename per input. Stem-based for readability; stems that
    appear more than once (two app.apk in different subdirectories) get
    a short path-hash suffix so outputs cannot collide. Computed over
    the FULL input list before sharding, so names are deterministic
    across independent array tasks."""
    import hashlib
    from collections import Counter

    ext = "json" if kind in JSON_OBJECT_WORKFLOWS else "jsonl"
    stems = Counter(p.stem for p in inputs)
    names = {}
    for p in inputs:
        if stems[p.stem] > 1:
            h = hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:8]
            names[p] = f"{p.stem}.{h}.{kind}.{ext}"
        else:
            names[p] = f"{p.stem}.{kind}.{ext}"
    return names


def output_path(outdir, input_path, kind):
    return Path(outdir) / f"{input_path.stem}.{kind}.jsonl"


def write_jsonl_atomic(path, records):
    """Write records to a temp file and rename into place. Paths ending
    .json get one pretty-printed object (the single record, or a list);
    .jsonl gets one compact JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w") as fh:
            if path.suffix == ".json":
                obj = records[0] if len(records) == 1 else records
                json.dump(obj, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            else:
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp.replace(path)           # atomic on POSIX filesystems
    finally:
        tmp.unlink(missing_ok=True)


def toolkit_version():
    try:
        return metadata.version("cim_app_histories")
    except metadata.PackageNotFoundError:
        return "unversioned"


from .analyse import (collect_all_files, extract_dex_urls,
                      analyse_flows, analyse_listening)


def base_record(input_path, kind):
    """Provenance carried by every output record, so results in a paper
    can be traced to the exact toolkit version that produced them."""
    return {
        "input": str(input_path),
        "analysis": kind,
        "toolkit_version": toolkit_version(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# ----------------------------------------------------------------------
# task functions (run in worker processes; must be importable, top-level)
# ----------------------------------------------------------------------

def task_classify(apk_path, options=None):
    """Detect ML runtimes/model binaries in one APK (androguard backend)."""
    from androguard.core.apk import APK
    from .classify.classify_so import ClassifySO

    apk = APK(str(apk_path))
    findings = ClassifySO().detect_ml_binaries(apk)
    base = base_record(apk_path, "classify")
    return [dict(base, **f) for f in findings] or [dict(base, finding=None)]



def task_flows(apk_path, options=None):
    """Trace inputs -> modules (libs/models) -> onward processes for one
    APK and return the flow graph. Pure data out; chains never emitted."""
    options = options or {}

    profiler = None
    if options.get("profile"):
        from .general.perf import StageProfiler
        profiler = StageProfiler()

    dx = None
    if options.get("trace"):
        from androguard.misc import AnalyzeAPK
        _, _, dx = AnalyzeAPK(str(apk_path))

    # analyse_flows does ingestion (split merge + dex urls); for profiling
    # we still want stage timings, so build via the shared path and attach.
    graph = analyse_flows(apk_path, dx=dx, profiler=profiler)
    rec = dict(base_record(apk_path, "flows"),
               graph=graph,
               sankey=graph.get("sankey"),
               summary=graph["summary"])
    if "warning" in graph:
        rec["warning"] = graph["warning"]
    if profiler is not None:
        rec["profile"] = profiler.report()
        profiler.close()
    return [rec]


def task_metadata(apk_path, options=None):
    """App metadata for one APK: identity, versions, permissions,
    activities, intents, localisation coverage, and A/B-testing SDKs
    (AB and localisation are part of this record; they are no longer
    separate commands)."""
    from .calls.metadata import extract_metadata

    return [dict(base_record(apk_path, "metadata"),
                 **extract_metadata(str(apk_path)))]


def task_listening(apk_path, options=None):
    """Trace audio inputs and their parameters through one app's
    processing chain (capture -> dsp -> features -> inference -> output)
    to models and network endpoints. Writes one .json object per app."""
    result = analyse_listening(apk_path)
    rec = dict(base_record(apk_path, "listening"), **result)
    return [rec]


TASKS = {
    "classify": task_classify,
    "flows": task_flows,
    "metadata": task_metadata,
    "listening": task_listening,
}


# ----------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------

def run_one(kind, input_path, outdir, force, options=None, out_name=None):
    """Process one input; never raises -- errors become records."""
    out = (Path(outdir) / out_name) if out_name else \
        output_path(outdir, input_path, kind)
    if out.exists() and not force:
        return ("skipped", input_path, out)
    try:
        records = TASKS[kind](input_path, options)
        write_jsonl_atomic(out, records)
        return ("ok", input_path, out)
    except Exception:
        err = dict(base_record(input_path, kind),
                   error=traceback.format_exc(limit=5))
        write_jsonl_atomic(out.with_suffix(".error.jsonl"), [err])
        return ("error", input_path, out)


def run_batch(kind, inputs, outdir, workers, force, options=None,
              out_names=None):
    out_names = out_names or {}
    statuses = {"ok": 0, "skipped": 0, "error": 0}
    if workers <= 1 or len(inputs) <= 1:
        results = (run_one(kind, p, outdir, force, options, out_names.get(p))
                   for p in inputs)
        for status, path, _ in results:
            statuses[status] += 1
            print(f"[{status}] {path}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_one, kind, p, outdir, force, options,
                                   out_names.get(p)) for p in inputs]
            for fut in as_completed(futures):
                status, path, _ = fut.result()
                statuses[status] += 1
                print(f"[{status}] {path}", file=sys.stderr)
    print(f"done: {statuses}", file=sys.stderr)
    return 1 if statuses["error"] else 0


def add_common(sub, input_flag, input_help):
    grp = sub.add_mutually_exclusive_group(required=True)
    grp.add_argument(input_flag, help=input_help)
    grp.add_argument(input_flag + "-list",
                     help="text file with one input path per line")
    grp.add_argument(input_flag + "-dir",
                     help="directory of .apk files (scanned in sorted "
                          "order; for very large or changing corpora, "
                          "generate a manifest once and use "
                          + input_flag + "-list for stability)")
    sub.add_argument("--recursive", action="store_true",
                     help="with " + input_flag + "-dir, also scan "
                          "subdirectories")
    sub.add_argument("--outdir", required=True, help="output directory")
    sub.add_argument("--workers", type=int, default=default_workers(),
                     help="parallel workers (default: CPUs allocated to this job)")
    sub.add_argument("--task-index", type=int, default=0,
                     help="this shard's index, e.g. $SLURM_ARRAY_TASK_ID")
    sub.add_argument("--task-count", type=int, default=1,
                     help="total shards, e.g. $SLURM_ARRAY_TASK_COUNT")
    sub.add_argument("--force", action="store_true",
                     help="reprocess inputs whose output already exists")


def _aggregate_metadata_csv(outdir, csv_path):
    """Collect every *.metadata.jsonl record under outdir into one CSV.
    Run as a post-pass so it captures outputs from all array shards that
    share the directory, not just this invocation's inputs."""
    from .calls.metadata import write_metadata_csv

    records = []
    for path in sorted(Path(outdir).glob("*.metadata.jsonl")):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    write_metadata_csv(records, csv_path)
    print(f"wrote {len(records)} rows to {csv_path}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cim-apps",
                                     description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {toolkit_version()}")
    subs = parser.add_subparsers(dest="command", required=True)

    s = subs.add_parser("classify", help="detect ML runtimes/models in APKs")
    add_common(s, "--apk", "path to one .apk file")

    s = subs.add_parser("metadata",
                        help="app identity, versions, permissions, "
                             "locales, and A/B SDKs per APK")
    add_common(s, "--apk", "path to one .apk file")
    s.add_argument("--csv", metavar="FILE",
                   help="after the run, aggregate all metadata records in "
                        "--outdir into one CSV (one row per app)")

    s = subs.add_parser("listening",
                        help="trace audio inputs and their parameters "
                             "through capture/dsp/features/inference to "
                             "models and endpoints (one .json per app)")
    add_common(s, "--apk", "path to one .apk file")

    s = subs.add_parser("flows",
                        help="trace inputs -> AI modules -> onward processes")
    add_common(s, "--apk", "path to one .apk file")
    s.add_argument("--trace", action="store_true",
                   help="strengthen links with dex method tracing (slower; "
                        "chains are summarised, never emitted)")
    s.add_argument("--profile", action="store_true",
                   help="record per-stage timing and memory into each "
                        "output record (adds tracemalloc overhead)")

    args = parser.parse_args(argv)

    all_inputs = collect_inputs(args.apk, args.apk_list, args.apk_dir,
                                getattr(args, "recursive", False))
    out_names = make_output_names(all_inputs, args.command)
    inputs = shard(all_inputs, args.task_index, args.task_count)

    if not inputs:
        print("no inputs in this shard; nothing to do", file=sys.stderr)
        return 0

    options = {"trace": getattr(args, "trace", False),
               "profile": getattr(args, "profile", False)}
    rc = run_batch(args.command, inputs, args.outdir, args.workers,
                   args.force, options, out_names)

    csv_path = getattr(args, "csv", None)
    if csv_path:
        _aggregate_metadata_csv(args.outdir, csv_path)

    return rc


if __name__ == "__main__":
    sys.exit(main())
