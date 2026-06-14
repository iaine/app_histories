# Running at scale

The same commands that analyse one app on a laptop analyse ten thousand
on a cluster. Three features make that work: deterministic sharding
(`--task-index`/`--task-count`), resumable outputs (existing results
are skipped), and atomic writes (a killed job never leaves a truncated
file that a restart would wrongly skip).

## SLURM array jobs

Divide a corpus across an array by passing the array variables through:

```bash
#!/bin/bash
#SBATCH --array=0-99
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=04:00:00

cim-apps metadata \
    --apk-dir /scratch/apps --outdir /scratch/results \
    --task-index "$SLURM_ARRAY_TASK_ID" \
    --task-count "$SLURM_ARRAY_TASK_COUNT"
```

Each array task processes its own deterministic shard; within a task,
work spreads across the allocated CPUs automatically (the worker count
respects `--cpus-per-task`, so do not set `--workers` by hand). If some
tasks fail or time out, resubmit the identical array: completed apps
skip, and only the gaps are reprocessed.

For corpora that are very large or still being downloaded, freeze a
manifest first and shard that instead of a directory:

```bash
find /scratch/apps -name '*.apk' | sort > corpus.txt
cim-apps metadata --apk-list corpus.txt --outdir /scratch/results \
    --task-index "$SLURM_ARRAY_TASK_ID" --task-count 100
```

## Containers (Apptainer)

Most clusters run Apptainer/Singularity rather than Docker. The
repository ships a definition file; build once (on a machine where you
have `--fakeroot` or root), then run the same image everywhere:

```bash
apptainer build cim-apps.sif apptainer.def
apptainer run --bind /scratch:/scratch cim-apps.sif metadata \
    --apk-dir /scratch/apps --outdir /scratch/results ...
```

The image pins the toolkit and its dependencies, so the laptop pilot
and the cluster run use bit-identical code — and the version recorded
in every output proves it.

## Sizing a run

Analysis cost is dominated by androguard parsing, roughly seconds per
app and scaling with APK size; the batch machinery itself adds well
under a millisecond per app. Before committing an allocation, pilot a
small shard with profiling:

```bash
head -20 corpus.txt > pilot.txt
cim-apps metadata --apk-list pilot.txt --outdir pilot/ --profile
```

The embedded profile (see the [profiling guide](../dev/profiling.md))
gives per-stage wall time and peak memory per app; multiply out for the
corpus, add headroom, and set `--time` and `--mem` from measurements
rather than guesses. Afterwards, reconcile against what SLURM actually
charged with `sacct --format=JobID,MaxRSS,Elapsed`.

## Filesystem etiquette

Parallel filesystems (Lustre, GPFS) prefer few large files over many
small ones. The toolkit's one-JSONL-per-app output is fine at the
tens-of-thousands scale, but keep `--outdir` on scratch rather than
home, and merge results into a single file or Parquet table for the
analysis phase:

```bash
cat /scratch/results/*.metadata.jsonl > corpus.metadata.jsonl
```
