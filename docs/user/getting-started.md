# Getting started

The CIM App Histories toolkit analyses Android APKs for digital-methods
research. It answers four kinds of question about an app, one per
workflow:

- **metadata** — what the app declares: identity, version, permissions,
  activities, the languages it ships, the A/B-testing SDKs and
  third-party trackers it bundles.
- **classify** — what AI/ML it carries: native runtime libraries
  (TensorFlow Lite, ONNX, vendor runtimes) and model files.
- **flows** — how data may move: device inputs (microphone, camera,
  files, streams…) → the modules that use them → onward to models and
  network endpoints.
- **listening** — the audio question in depth: how sound is captured,
  conditioned, turned into features, fed to a model, and sent onward,
  with the audio parameters (sample rate, channels, mel bins…) at each
  stage.

It runs the same way on a laptop and on an HPC cluster, over one app or
a corpus of thousands. The toolkit is alpha software under active
development; output fields may change between versions, and every output
record records the toolkit version that produced it.

## Requirements

- Python 3.10 or newer
- The APKs you want to analyse (see *A note on where APKs come from*
  below — this matters more than it sounds)

## Installation

From a clone of the repository:

```bash
git clone https://github.com/iaine/app_histories.git
cd app_histories
pip install -e .
```

This installs the runtime dependencies (androguard 4.x, pandas,
networkx, loguru) and creates the `cim-apps` command. Two optional
extras exist:

```bash
pip install -e ".[viz]"    # plotting stack (matplotlib, numpy, Pillow)
pip install -e ".[dev]"    # pytest + ruff for contributors
```

The `viz` extras are kept separate so cluster environments stay free of
GUI toolkits. Confirm the install:

```bash
cim-apps --version
```

## Running the tool

**Always run it as the installed command or as a module — never as a
file path.** This is the most common first stumble:

```bash
cim-apps metadata --apk MyApp.apk --outdir results/                          # correct
python -m cim_app_histories.cli metadata --apk MyApp.apk --outdir results/   # also correct
python src/cim_app_histories/cli.py                                          # WRONG — will error
```

Running the raw `.py` file fails with *"attempted relative import with
no known parent package"*, because executing a file by path strips its
package context and the internal imports can't resolve. Use `cim-apps`
(the entry point created at install) or `python -m`.

## Your first run

Point a workflow at one APK and an output directory:

```bash
cim-apps metadata --apk MyApp.apk --outdir results/
```

This writes `results/MyApp.metadata.jsonl` — one JSON object with the
app's identity, permissions, languages, A/B SDKs and trackers. Try the
other workflows the same way:

```bash
cim-apps classify  --apk MyApp.apk --outdir results/
cim-apps flows     --apk MyApp.apk --outdir results/
cim-apps listening --apk MyApp.apk --outdir results/
```

`flows` and `metadata` write `.jsonl`; `listening` writes a single
pretty-printed `.json` per app.

## Analysing a whole folder

For a corpus, swap `--apk` for `--apk-dir`:

```bash
cim-apps metadata --apk-dir apps/ --outdir results/
```

One output file is written per app, work is spread across your CPU
cores automatically, and **already-completed apps are skipped on
re-run** — so an interrupted run resumes just by running the same
command again. Add `--recursive` to include subdirectories, or use
`--apk-list corpus.txt` to drive from a file of paths (best for large or
still-downloading corpora). See the [command reference](cli.md) for all
options, and [running at scale](hpc.md) for SLURM arrays and containers.

## A note on where APKs come from

This catches people out, so it is worth stating plainly. Apps installed
from Google Play or pulled off a device arrive as a **split App
Bundle**: a `base.apk` plus several `split_config.*.apk` files. The
native libraries — where much of the AI lives — are in the split files,
**not** the base. Analysing the base alone finds no native libraries and
produces near-empty `flows`/`listening`/`classify` results.

Two ways to get complete results:

1. **Use a universal APK.** Sites like APKPure provide a single APK with
   everything bundled in. This is the simplest path.
2. **Keep the splits together.** Put `base.apk` and its
   `split_config.*.apk` files in the same folder; the toolkit detects
   and merges them automatically.

When a workflow finds no native libraries and no splits, it adds a
`warning` field to the output explaining this — so an empty result tells
you *why* it is empty rather than failing silently.

## Looking at results

Results are JSON Lines (or JSON for `listening`); load them with pandas:

```python
import json, pathlib, pandas as pd
rows = [json.loads(l)
        for p in pathlib.Path("results").glob("*.metadata.jsonl")
        for l in open(p)]
df = pd.DataFrame(rows)
```

Or analyse a single APK directly in a notebook, without the CLI:

```python
from cim_app_histories.analyse import analyse_flows, analyse_listening
graph = analyse_flows("MyApp.apk")
audio = analyse_listening("MyApp.apk")
```

For a quick visual, the browser-based [Sankey and metadata
viewers](visualising.md) render any result file with no setup — just
drag the file in.

## Where next

- [Command reference](cli.md) — every workflow and option, with recipes
- [Working with results](results.md) — loading and analysing outputs
- [Listening workflow](listening.md) — the audio chain in detail
- [Visualising results](visualising.md) — the Sankey and metadata viewers
- [Running at scale](hpc.md) — SLURM arrays, containers, profiling
- [Methods](../methods.md) — research methodology and the limits of the
  evidence

## A word on the evidence

Everything the toolkit reports is **static-analysis evidence**: declared
permissions, strings and signatures present in the package, URLs found
in code. It shows what an app *can* do and what it is *built to do*, not
a recording of runtime behaviour. Detections are heuristic and meant to
be audited — treat a sample by hand before reporting findings, and see
the methods page for where the evidence is strong and where it is only
suggestive.
