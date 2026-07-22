# DEX tracing in `flows`

`flows` originally read one thing: the strings inside an app's native
libraries (`.so` files). That works well for apps whose audio pipeline is
compiled native code, but it misses apps that do the same work in
Java/Kotlin — and it turns out many do.

The clearest case is Otter, a transcription app. Its universal APK holds
2,662 files and 12 native libraries, and **every one of those libraries is
graphics code**. There is no audio library at all: Otter records through
Android's `AudioRecord` API in Java/Kotlin and transcribes server-side. So
`flows` used to report `camera` and `file` for a voice-recording app, and no
microphone.

DEX tracing closes that gap. It reads the app's compiled Java/Kotlin
bytecode (the `classes*.dex` files) and looks for calls to the Android
framework APIs that capture audio and send data over the network.

Nothing changes in how you run `flows`; the tracing is on by default.

```bash
cim-apps flows --apk app.apk --outdir results/
```

## What it detects

**Audio capture.** A call to `AudioRecord`, `MediaRecorder`, or
`MediaProjection` in the app's bytecode. Otter now reports `microphone`
alongside `camera` and `file`.

**Network egress.** Calls to the HTTP and socket libraries an app uses to
send data off the device: OkHttp, Retrofit, gRPC, `HttpURLConnection`,
Volley, raw sockets, and `WebView.loadUrl`.

The evidence is always an actual **call**, never a mention. A class name
appearing as a string constant does not count; neither does a permission.
An app can declare `RECORD_AUDIO` and never record — the permission is a
capability, so on its own it never creates a link. When a permission *does*
accompany a real call, it is recorded as corroboration and adds to the
score.

## Reading the output

Two kinds of entry appear, both marked `"source_layer": "dex"` so you can
tell at a glance that the evidence came from bytecode rather than a native
library.

A capture entry:

```json
{
  "modality": "audio",
  "stage": "capture",
  "module": "app_code",
  "input": "microphone",
  "source_layer": "dex",
  "operations": ["AudioRecord"]
}
```

And the corresponding link, showing the permission corroborating the call:

```json
{
  "source": "microphone",
  "target": "app_code",
  "kind": "feeds",
  "score": 3,
  "evidence": {
    "dex_api": ["AudioRecord"],
    "source_layer": "dex",
    "permissions": ["android.permission.RECORD_AUDIO"]
  }
}
```

Note the target is `app_code`, not a named library. That is deliberate: the
evidence is in the app's own bytecode, so the graph says "app code captures
audio" rather than attributing it to a library that is not responsible.

An egress entry looks like this:

```json
{
  "modality": "audio",
  "stage": "output",
  "module": "app_code",
  "input": "microphone",
  "source_layer": "dex",
  "operations": ["okhttp3", "retrofit2"],
  "evidence": {
    "proximity": "method",
    "relation": "co-occurrence",
    "capture": ["AudioRecord"]
  }
}
```

## `proximity` — the field that matters most

**This is the part to read carefully, because it is what stops the egress
finding being over-claimed.**

The trace reports *co-occurrence*, not dataflow. It tells you that capture
and network APIs are called near each other in the code — it does **not**
prove that the recorded audio is what gets sent. Proving that requires
tracking the actual bytes through the program (taint analysis), which this
toolkit does not do.

`proximity` grades how close the two are:

| Value | Meaning | How to read it |
|-------|---------|----------------|
| `"method"` | One method calls both a capture API and a network API | Strongest. The recording and sending code are in the same function. |
| `"class"` | The same class does both, in different methods | Moderate. Plausibly one component handling both. |
| `null` | Both APIs exist in the app, but in unrelated classes | Weakest. The app records, and the app networks. Nothing links them. |

Real Otter returns **`null`** — recording and uploading live in separate
classes, which is exactly how a well-structured app is written. That is an
honest result, not a failure of detection. Otter certainly does upload
audio; the trace simply cannot evidence the connection from static
structure alone, and says so rather than implying a link it cannot support.

Treat `null` as "both capabilities present, relationship unknown". Treat
`"method"` as a strong lead worth manual inspection. In writing, phrase
findings accordingly: *"the app records audio and contacts these
endpoints"* is supportable; *"the app sends recordings to these
endpoints"* is not, unless you have confirmed it another way.

## Filtering DEX-sourced findings

Because every DEX entry is tagged, separating the two evidence layers is
straightforward:

```python
import json

rec = json.load(open("results/app_flows.jsonl"))

dex = [e for e in rec["chain"] if e.get("source_layer") == "dex"]
native = [e for e in rec["chain"] if e.get("source_layer") != "dex"]
```

To find apps in a corpus where capture and egress are strongly co-located:

```python
strong = [
    e for e in rec["chain"]
    if e.get("stage") == "output"
    and e.get("evidence", {}).get("proximity") == "method"
]
```

## Cost, and turning it off

The egress trace is a second full pass over every method in every DEX file.
On a large app this takes roughly **40 seconds** (measured on Otter, seven
DEX files, ~60,000 methods in the first alone). Capture detection is
cheap; it is the egress trace that carries the cost.

For corpus runs where you only need the inputs, switch it off:

```bash
cim-apps flows --apk-dir corpus/ --outdir results/ --no-dex-trace
```

From a notebook:

```python
from cim_app_histories.analyse import analyse_flows

graph = analyse_flows("app.apk", dex_trace=False)
```

Capture detection still runs with `--no-dex-trace`; only the
capture-to-egress trace is skipped.

## Limitations

**Static, not runtime.** A call existing in the bytecode does not mean it
runs, or runs often. It may sit behind a condition that never fires.

**Co-occurrence, not dataflow.** Restated because it matters: `proximity`
describes code layout, not data movement. See above.

**MediaRecorder can over-claim.** `MediaRecorder` records video with audio
as well as audio alone, so an app that only films may be reported as
capturing audio. Bounded and known; check the app before relying on it.

**Obfuscation.** R8/ProGuard renames application classes but cannot rename
framework classes, so `AudioRecord` and `HttpURLConnection` survive
obfuscation. Third-party library prefixes (`okhttp3`, `retrofit2`) survive
ordinary builds, but a fully shaded build could hide them. Reflection —
calling an API by name at runtime — evades detection entirely. All of these
cause **under**-reporting, which is the safe direction: the tool claims
less than the truth, never more.

**Microphone only, for now.** Camera and location capture in Java/Kotlin
are not yet detected through the DEX. The mechanism is table-driven, so
adding them is a small change.

## See also

- [Working with results](results.md) — loading JSONL into pandas
- [CLI reference](cli.md) — all flags
- [Visualising flows](visualising.md) — the Sankey viewer
