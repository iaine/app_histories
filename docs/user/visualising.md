# Visualising results

A small self-contained viewer renders the `flows` and `listening`
outputs as Sankey diagrams — no install, no server, no build step.

## Using it

Open `docs/viewer/sankey.html` in any browser and drag result files
onto it (or click to choose). You can drop **one file or many at once**,
and the viewer picks the right view automatically:

* **One app** → a Sankey diagram of that app's flow.
* **Many versions of one app** (same package, different version
  numbers) → a *version timeline*: a table of sources, tasks, endpoints,
  and parameter transitions per version, with anything gained since the
  previous version marked green and anything removed struck through.
* **Many different apps** (different packages) → an *app comparison*: a
  presence matrix showing which sources, tasks, and endpoints each app
  has, so Spotify, Deezer, TikTok and Otter line up side by side.

A mode toggle lets you override the automatic choice — e.g. force the
comparison view onto a set of versions, or open any single app's Sankey
from a corpus. The scenario is inferred from the package names in the
files: identical package = versions, differing = comparison.

The diagram colours nodes by role. For `flows`: inputs, modules,
models, endpoints. For `listening`: the five processing stages
(capture → dsp → features → inference → output), plus sources, models,
and endpoints. Hover any link to see the evidence behind it — the
keywords, APIs, or URL categories that justified it — and hover a node
for its kind.

For `listening` records, parameter transitions appear below the
diagram as chips: `sample_rate: [48000] → [16000] (capture→dsp)`. These
are the signal-shape changes the workflow detected between stages.

## Reading a listening diagram

Left to right follows the audio chain. A speech-to-text app reads as
microphone → capture library → (dsp, features stages) → a model and a
task label, with an upload endpoint at the right edge; the transition
chips below show the 48 kHz→16 kHz, stereo→mono collapse that marks an
ASR front end. A music app reads from a network-stream source into
analysis features and a recommendation task ending at a recommendation
endpoint — and shows no microphone branch, because none was evidenced.

## Sample files

`docs/viewer/samples/` contains synthetic `Demo.flows.jsonl`,
`STT.listening.json`, and `Music.listening.json` so you can see the
viewer working before running the toolkit on real APKs. These are
schematic illustrations, not analyses of real apps.

## Notes and limits

The viewer is read-only and runs entirely in the browser, so result
files never leave your machine — safe for sensitive corpora. It loads
d3 and d3-sankey from a CDN, so the first open needs network access
(cache it, or vendor the two scripts locally for fully offline use).
Link widths reflect evidence scores, not measured data volume, and the
diagram inherits every caveat of the underlying static analysis:
treat it as a map of evidenced *possibility*, not observed runtime
behaviour. For a whole-corpus view rather than one app at a time,
aggregate the JSON in pandas (see [Working with results](results.md))
and feed your own totals to a plotting library.

## The flow viewer

Open `docs/viewer/sankey.html` and drop in one or more `*.flows.jsonl`
or `*.listening.json` files. Three views:

**Pipeline** (one app) is the default: a Sankey whose **columns are the
processing stages** — capture → preprocess → features → inference →
output — and whose **colours are the modality** (audio, video, image,
text, sensor, location, network). Each block is one (modality, stage)
bucket, labelled with how many native libraries fall in it; hover for
the operations, parameters, models and endpoint counts behind it.

Two things make this readable on real apps. Blocks aggregate: TikTok's
4,600 chain entries across 500+ libraries collapse to about 30 blocks
rather than a 2,000-node hairball. And **stages a modality does not use
are skipped** — location shows capture → preprocess → features →
output with no inference column drawn, because none was evidenced.

Below the diagram, parameter transitions are listed per modality
(`audio sample_rate: [48000] → [16000] (capture→features)`).

The colour chips above the diagram double as **filters**: click a
modality to hide it, which is the quickest way to read one pipeline in
an app that does everything.

**Detail** is the same aggregation as a table — modality, stage, module
count, operations, parameters, models/endpoints — for reading exact
values or copying them out.

**Compare apps** (several files) puts one row per app and shows which
stages each modality reaches, e.g. `C→P→F→I→O`, plus a transition
count. It is the fastest way to see that one app captures audio but
another only streams it.

## Metadata visualisations

The `metadata` output is categorical rather than a flow, so it has its
own viewer: open `docs/viewer/metadata.html` and drop one or more
`*.metadata.jsonl`/`.json` files. As with the flow viewer, the view is
chosen automatically and can be overridden with the mode toggle:

* **One app → dashboard.** Counts of permissions, languages, A/B and
  analytics SDKs, and activities, with the full lists below; sensitive
  permissions (microphone, camera, location, contacts...) are flagged
  in red.
* **Many versions of one app → growth timeline.** A line chart of
  permission/language/SDK counts across versions, plus a table showing
  exactly what each version *added* (green) or *removed* (struck) since
  the previous one. This is where a study can see, for example, the
  version at which an app first requested microphone access or adopted
  a new analytics SDK.
* **Many apps → comparison.** Summary cards plus presence matrices for
  permissions, SDKs, and languages, so a set like Spotify / Deezer /
  TikTok / Otter lines up feature by feature; sensitive permissions are
  highlighted across the matrix.

Sample files live in `docs/viewer/samples/` (a three-version series and
a four-app set). These are schematic illustrations, not analyses of the
named apps.


The metadata viewer also has an **Export CSV** button that downloads whatever records are loaded as a spreadsheet — identical columns to the CLI's `--csv`, so the two are interchangeable.
