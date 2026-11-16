# network: the tracker call graph

`network` records, for every app, which code calls into third-party
tracker SDKs and what the tracker code calls in turn:

    app code  ->  tracker SDK  ->  network API / framework / library

It then combines every app into **one GraphML file** for Gephi or
networkx.

```bash
# 1. metadata first: this is where the tracker lists come from
cim-apps metadata --apk-dir apks/ --outdir results/

# 2. the tracker call graph
cim-apps network --input-dir results/ --apk-dir apks/ --outdir results/
```

`--input-dir` is the directory of `*.metadata.jsonl` files. Their tracker
lists are read once into a single shared set, and every APK is scanned
for the whole set.

## Outputs

| File | Contents |
|------|----------|
| `<apk>.network.jsonl` | one record per app: `pkg`, `version`, `graph.nodes`, `graph.links`, `summary` |
| `network.graphml` | every app combined, written after the last APK (`--graphml FILE` to rename) |

Node `kind` is one of:

- `tracker`: a method in a tracker package, with `tracker` (signature) and `category`
- `app`: code shipped in the APK outside every tracker (the app and its bundled libraries)
- `network_api`: OkHttp, Retrofit, `HttpURLConnection`, sockets, gRPC, Volley, `WebView.loadUrl`
- `external`: anything the APK only refers to (the Android framework, the JDK)

Link `kind` is `calls_tracker`, `tracker_calls`, `network`,
`tracker_to_tracker` or `internal`. `weight` is the number of call sites.

In the combined graph, tracker, network and external nodes are shared
between apps, so two apps using the same SDK meet at the same nodes;
`apps` says how many apps a node or edge was seen in. App-code nodes are
kept apart per app (`<pkg>::<id>`), because two apps both having a class
`La/b;` share only an obfuscated name.

## Options

- `--level class` gives one node per class instead of per method. On three
  test apps this cut the graph from 32,683 edges to 14,126.
- `--include-internal` keeps calls that stay inside one tracker. They are
  dropped by default: they were nearly half of all edges on a real app.

## SLURM arrays

With `--task-count` above 1 no shard writes the combined graph. Run the
merge once the array has finished:

```bash
cim-apps network-merge --outdir results/
```

## Cost

One pass over the bytecode: about 40 seconds and 0.9 GB for a mid-sized
app (Otter, 312,000 methods). Very large apps take several times that, so
keep `--workers` low for them.

## Limits

- An edge means "this method contains a call to that one". Interface
  dispatch and reflection are not resolved, so the graph under-reports.
- Only trackers already named in the metadata results are searched for.
- Shared tracker nodes are matched by name. Two SDK versions that
  obfuscate an internal method to the same name are merged.
