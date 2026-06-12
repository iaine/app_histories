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
    cim-apps ab --decompiled extracted/app/ --outdir results/

HPC (SLURM array over a corpus list, one shard per array task):
    cim-apps classify --apk-list corpus.txt --outdir results/ \\
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


def collect_inputs(single, list_file):
    if single:
        return [Path(single)]
    paths = [Path(line.strip()) for line in Path(list_file).read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    return paths


def output_path(outdir, input_path, kind):
    return Path(outdir) / f"{input_path.stem}.{kind}.jsonl"


def write_jsonl_atomic(path, records):
    """Write records to a temp file and rename into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w") as fh:
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

def task_classify(apk_path):
    """Detect ML runtimes/model binaries in one APK (androguard backend)."""
    from androguard.core.apk import APK
    from .classify.classify_so import ClassifySO

    apk = APK(str(apk_path))
    findings = ClassifySO().detect_ml_binaries(apk)
    base = base_record(apk_path, "classify")
    return [dict(base, **f) for f in findings] or [dict(base, finding=None)]


def task_ab(decompiled_dir):
    """A/B-testing SDK signatures in one JADX-decompiled directory."""
    from .ab.ab import AB

    ab = AB()
    classes = ab.get_classes(str(decompiled_dir).rstrip("/") + "/")
    hits = ab.find_ab_by_package(str(decompiled_dir), classes)
    base = base_record(decompiled_dir, "ab")
    return [dict(base, signature=h) for h in hits] or [dict(base, signature=None)]


def task_localisation(decompiled_dir):
    """Locale resource qualifiers in one JADX-decompiled directory."""
    from .localisation.localisation import Locales

    loc = Locales()
    folders = sorted(loc.get_values(str(decompiled_dir)))
    base = base_record(decompiled_dir, "localisation")
    out = []
    for folder in folders:
        out.append(dict(
            base,
            resource_dir=folder,
            language=loc.extract_language(folder),
            country=loc.extract_country(folder),
        ))
    return out or [dict(base, resource_dir=None)]


TASKS = {
    "classify": task_classify,
    "ab": task_ab,
    "localisation": task_localisation,
}


# ----------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------

def run_one(kind, input_path, outdir, force):
    """Process one input; never raises -- errors become records."""
    out = output_path(outdir, input_path, kind)
    if out.exists() and not force:
        return ("skipped", input_path, out)
    try:
        records = TASKS[kind](input_path)
        write_jsonl_atomic(out, records)
        return ("ok", input_path, out)
    except Exception:
        err = dict(base_record(input_path, kind),
                   error=traceback.format_exc(limit=5))
        write_jsonl_atomic(out.with_suffix(".error.jsonl"), [err])
        return ("error", input_path, out)


def run_batch(kind, inputs, outdir, workers, force):
    statuses = {"ok": 0, "skipped": 0, "error": 0}
    if workers <= 1 or len(inputs) <= 1:
        results = (run_one(kind, p, outdir, force) for p in inputs)
        for status, path, _ in results:
            statuses[status] += 1
            print(f"[{status}] {path}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_one, kind, p, outdir, force) for p in inputs]
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
    sub.add_argument("--outdir", required=True, help="output directory")
    sub.add_argument("--workers", type=int, default=default_workers(),
                     help="parallel workers (default: CPUs allocated to this job)")
    sub.add_argument("--task-index", type=int, default=0,
                     help="this shard's index, e.g. $SLURM_ARRAY_TASK_ID")
    sub.add_argument("--task-count", type=int, default=1,
                     help="total shards, e.g. $SLURM_ARRAY_TASK_COUNT")
    sub.add_argument("--force", action="store_true",
                     help="reprocess inputs whose output already exists")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cim-apps",
                                     description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {toolkit_version()}")
    subs = parser.add_subparsers(dest="command", required=True)

    s = subs.add_parser("classify", help="detect ML runtimes/models in APKs")
    add_common(s, "--apk", "path to one .apk file")

    s = subs.add_parser("ab", help="detect A/B-testing SDKs in decompiled apps")
    add_common(s, "--decompiled", "path to one JADX output directory")

    s = subs.add_parser("localisation", help="extract locale qualifiers")
    add_common(s, "--decompiled", "path to one JADX output directory")

    args = parser.parse_args(argv)

    single = getattr(args, "apk", None) or getattr(args, "decompiled", None)
    listing = getattr(args, "apk_list", None) or getattr(args, "decompiled_list", None)
    inputs = shard(collect_inputs(single, listing), args.task_index, args.task_count)

    if not inputs:
        print("no inputs in this shard; nothing to do", file=sys.stderr)
        return 0

    return run_batch(args.command, inputs, args.outdir, args.workers, args.force)


if __name__ == "__main__":
    sys.exit(main())
