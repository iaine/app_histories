# Command reference

All analysis runs through one command, `cim-apps`, with three
workflows. Every workflow shares the same input and batching options,
so anything you learn about running one applies to the others.

```
cim-apps {metadata, classify, flows} [input] --outdir DIR [options]
```

## Choosing inputs

Exactly one of three input modes:

`--apk PATH` analyses a single APK file.

`--apk-dir DIR` analyses every `.apk` file in a directory (add
`--recursive` to include subdirectories). Files are processed in sorted
order; hidden files and non-APK files are ignored. A directory may of
course contain just one app. For very large corpora, or folders that a
scraper is still writing into, prefer a manifest: the file list must be
identical every time the command runs for array sharding to divide it
safely.

`--apk-list FILE` reads one APK path per line from a text file (`#`
comments allowed). Generate one once with, for example,
`find /scratch/apps -name '*.apk' | sort > corpus.txt`.

## Common options

`--outdir DIR` (required) is where results go: one
`<app>.<workflow>.jsonl` file per input. If two inputs share a
filename (two `app.apk` in different folders), a short hash is added so
outputs never collide. Failures produce an `<app>.<workflow>.error.jsonl`
file instead of stopping the batch.

`--workers N` sets parallel processes; the default is the number of
CPUs actually allocated to the job (it respects SLURM and container
limits), so you rarely need to set it.

`--force` reprocesses inputs whose output file already exists. Without
it, completed apps are skipped — which is what makes interrupted runs
resumable: just run the same command again.

`--task-index I` / `--task-count N` divide the input list into N
deterministic shards and process only shard I. These map directly onto
SLURM array variables; see [Running at scale](hpc.md).

## metadata

```bash
cim-apps metadata --apk-dir apps/ --outdir results/
```

One record per app: application name, package, version code and name,
permissions, activities, intents, localisation coverage (which
language/region resource sets the app ships, e.g. `["zh", "CN", ""]`),
and the A/B-testing SDKs detected in its code (all `classes*.dex` files
are scanned, so multidex apps are fully covered). This is the
per-version observable set that app-histories studies track across
releases — A/B and localisation are fields of this record, not separate
commands.

### Exporting metadata to CSV

`metadata` accepts `--csv FILE`: after the run it aggregates every
metadata record in `--outdir` into one CSV, one row per app, with the
categorical fields flattened to counts plus `;`-joined lists
(permissions, sensitive permissions, languages, A/B SDKs). Because it
reads the written outputs rather than memory, it also gathers results
from all SLURM array shards that share the directory:

```bash
cim-apps metadata --apk-dir apps/ --outdir results/ --csv corpus.csv
```

## classify

```bash
cim-apps classify --apk-dir apps/ --outdir results/
```

Detects AI/ML components: native runtime libraries (TensorFlow Lite,
ONNX Runtime, and proprietary vendor runtimes detected heuristically)
and model files, with inferred vendor and category. Detections are
heuristic — treat them as evidence to audit, not ground truth, and see
the [methods](../methods.md) page for how thresholds are set.

## flows

```bash
cim-apps flows --apk app.apk --outdir results/ [--trace] [--profile] [--no-dex-trace]
```

Builds a graph per app of how data may flow: device inputs (microphone,
camera, Bluetooth/MIDI, text, network streams, files, sensors, screen)
linked to the modules that show evidence of using them (native
libraries and the model files they reference), linked onward to network
endpoints and produced outputs. Links require co-located evidence in
the module's own strings — keyword tables cover English and Chinese —
and each link records the evidence behind it. The output includes
Sankey-ready edges for visualisation.

`--trace` strengthens links using dex method tracing (substantially
slower; the traced chains are summarised into evidence, never emitted).
`--profile` embeds per-stage timing and memory into each record — see
the [profiling guide](../dev/profiling.md).

`--no-dex-trace` skips the capture-to-egress DEX trace, which is a second
pass over every method (~40s on a large app). Audio capture detection still
runs. See [DEX tracing](dex-tracing.md) for what the trace finds and how to
read the `proximity` field.

## listening

```bash
cim-apps listening --apk-dir apps/ --outdir results/
```

The audio-specialist workflow: traces audio inputs only (microphone,
streams, files, Bluetooth/MIDI) through the canonical chain capture →
dsp → features → inference → output, extracting the audio parameters
visible at each stage (sample rates, channels, frame/hop sizes, mel
bins, codecs) and recording where they change between stages. Outputs
one pretty-printed `.json` document per app rather than JSONL. See the
[listening guide](listening.md) for the stage model and worked
examples.

## Recipes

Resume an interrupted corpus run (completed apps skip automatically):

```bash
cim-apps metadata --apk-dir apps/ --outdir results/
```

Re-run everything after upgrading the toolkit:

```bash
cim-apps metadata --apk-dir apps/ --outdir results-v2/   # or --force
```

Pilot ten apps with profiling before committing a cluster allocation:

```bash
head -10 corpus.txt > pilot.txt
cim-apps flows --apk-list pilot.txt --outdir pilot/ --profile
```
