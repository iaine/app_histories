# Getting started

The CIM App Histories toolkit analyses Android APKs for digital-methods
research: what an app declares (permissions, activities, locales), which
A/B-testing SDKs it ships, what AI/ML runtimes and models it carries,
and how data may flow from device inputs (microphone, camera, files)
through those components to network endpoints. It is built to run the
same way on a laptop and on an HPC cluster, over one app or a corpus of
thousands.

The toolkit is alpha software under active development; commands and
output fields may change between versions. Every output record carries
the toolkit version that produced it, so results remain traceable.

## Installation

Requires Python 3.10 or later.

```bash
git clone https://github.com/iaine/app_histories.git
cd app_histories
pip install -e .
```

This installs the runtime dependencies (androguard 4.x, pandas,
networkx, loguru) and the `cim-apps` command. Two optional extras
exist: `pip install -e ".[viz]"` adds the plotting stack (matplotlib,
numpy, Pillow — deliberately not installed by default so cluster
environments stay free of GUI toolkits), and `".[dev]"` adds pytest and
ruff for contributors.

Check the install:

```bash
cim-apps --version
```

For containerised installs (recommended on HPC), see
[Running at scale](hpc.md).

## First run

Point a workflow at one APK and an output directory:

```bash
cim-apps metadata --apk MyApp.apk --outdir results/
```

This writes `results/MyApp.metadata.jsonl`: one JSON object containing
the app's identity, versions, permissions, activities, intents, locale
coverage, and detected A/B-testing SDKs. The other two workflows are
`classify` (AI/ML runtimes and model files) and `flows` (input → module
→ endpoint graphs); all three take the same input and batching options.

To analyse a folder of apps — the common case for a scraped corpus —
swap `--apk` for `--apk-dir`:

```bash
cim-apps metadata --apk-dir apps/ --outdir results/
```

One output file is written per app, already-completed apps are skipped
on re-run, and the work is spread across your CPU cores automatically.

## Where next

The [command reference](cli.md) describes each workflow and option.
[Working with results](results.md) shows how to load the JSONL outputs
into pandas. [Running at scale](hpc.md) covers SLURM arrays, containers,
and profiling for corpus-sized studies. Research methodology lives on
the [methods](../methods.md) page.
