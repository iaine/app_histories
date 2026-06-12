# Working with results

Every workflow writes JSON Lines: one file per app, one JSON object per
line. JSONL is append-safe, streams well at corpus scale, and loads
directly into pandas. Every record carries provenance — the input path,
the workflow name, the toolkit version, and a timestamp — so any number
in a paper can be traced to the run that produced it.

## Loading a corpus into pandas

```python
import json, pathlib
import pandas as pd

records = []
for path in pathlib.Path("results").glob("*.metadata.jsonl"):
    with open(path) as fh:
        records.extend(json.loads(line) for line in fh)

df = pd.DataFrame(records)
```

From there, typical questions are one-liners. Which A/B frameworks are
most common across the corpus:

```python
df.explode("ab")["ab"].value_counts()
```

Language coverage per app (the localisation field holds
`[language, region, device]` triples):

```python
df["languages"] = df["localisation"].apply(
    lambda locs: sorted({l[0] for l in locs}))
```

Tracking change across versions of the same app — the core
app-histories move — groups on the package name and sorts by version
code:

```python
history = (df.sort_values("version_code")
             .groupby("pkg")["ab"].apply(list))
```

## The flows graph

Each `*.flows.jsonl` record contains a `graph` (nodes and links), a
`summary`, and `sankey` edges ready for plotting libraries. Every link
carries its evidence:

```python
rec = json.loads(open("results/MyApp.flows.jsonl").read())
for link in rec["graph"]["links"]:
    if link["kind"] == "feeds":
        print(link["source"], "->", link["target"],
              link["score"], link["evidence"]["keywords"])
```

The `score` is an evidence count, not a probability: a link backed by
an API reference, two keywords, and a corroborating permission scores
higher than one backed by a single keyword, and the evidence lists let
you audit exactly why a link exists. When reporting findings, audit a
sample of links by hand first.

## Errors and skips

A failed app produces `<app>.<workflow>.error.jsonl` containing the
input path and a traceback, rather than halting the batch. Count and
inspect them before analysis:

```bash
ls results/*.error.jsonl | wc -l
```

A healthy corpus run ends with a summary line on stderr, e.g.
`done: {'ok': 9961, 'skipped': 0, 'error': 39}`. Skipped means an
output file already existed (resume behaviour); errors deserve a look —
malformed APKs and truncated downloads are the usual causes.
