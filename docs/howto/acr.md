# ACR: detecting automatic content recognition

The `acr` workflow answers one question: does an app contain **automatic
content recognition** for audio — the Shazam-style capability of listening
through the microphone, computing an acoustic fingerprint, and matching it
against a cloud catalogue to identify what is playing?

ACR is a distinct research object from generic microphone use. A voice-notes
app records audio; an ACR-enabled app records audio *in order to recognise
what is playing in the room*. The privacy and platform-power questions are
different, so `acr` reports it as its own graded signal rather than folding
it into `flows`.

```bash
cim-apps acr --apk app.apk --outdir results/
cim-apps acr --apk-dir apps/ --outdir results/
cim-apps acr --apk app.xapk --outdir results/     # bundles work too
```

Output is one JSONL record per app, with the usual batching, sharding, and
resume behaviour of the other workflows.

## What it looks for

Four independent signals, plus a keyword tier, because any single signal has
a benign explanation:

1. **SDK package** (strongest) — a named ACR vendor's classes shipped in the
   app: ACRCloud, Shazam, Gracenote, SoundHound/Houndify, AudD, and others.
2. **Fingerprinting native library** (strong) — a purpose-built `.so` such
   as `libfingerprint_jni.so` or NetEase's `libNeSRAudioRecAndFpExtractor.so`.
3. **Recognition endpoint** (strong) — a URL path like `/v1/identify`,
   `/api/recognize`, or an ACRCloud/Houndify host.
4. **Capture + egress** (corroborating) — the app records audio *and*
   reaches the network.

Plus a **CJK keyword** tier for Chinese-market "听歌识曲" (listen-to-identify)
features. Keywords are **corroboration only** — a feature label can name a
chart or outlive a removed feature, so a keyword never raises confidence on
its own.

Permissions (`RECORD_AUDIO`, `INTERNET`, `FOREGROUND_SERVICE_MICROPHONE`)
are recorded but never a signal in their own right: a permission is a
capability, not evidence of use.

## The `confidence` field — read this carefully

The workflow grades `high` / `medium` / `low` / `none`. **This is the field
to understand, because it is what keeps the result honest.**

| Confidence | Rule of thumb | How to read it |
|-----------|---------------|----------------|
| `high` | a named SDK, or ≥2 strong signals, or several fingerprint libraries | A specific ACR vendor is shipped, or independent evidence agrees. Strong. |
| `medium` | one strong signal + capture behaviour | ACR-shaped, vendor not named. Worth inspecting. |
| `low` | capture + egress only | Records and networks. Could be ACR, could be any uploading recorder. |
| `none` | no primary signal | No ACR evidence — even if a keyword matched. |

**A keyword match with no primary signal grades `none`, not `low`.** This is
deliberate and important: a music player can display a chart called
"听歌识曲" ("listen-to-identify chart") without doing any recognition itself.
That app has the *words* but none of the *capability*, and the workflow must
not flag it. See the validation below for a real example.

## Reading the output

```json
{
  "input": "…/app.apk",
  "analysis": "acr",
  "app": {"pkg": "com.netease.cloudmusic", "version": "9.5.05"},
  "acr": {
    "confidence": "high",
    "vendors": [],
    "native_libs": [
      {"library": "libnesraudiorecandfpextractor.so", "vendor": "NetEase",
       "pattern": "libnesraudiorecandfpextractor", "confidence": "confirmed"}
    ],
    "endpoints": [
      {"url": "https://identify.acrcloud.com/v1/identify",
       "pattern": "/v1/identify", "vendor": "ACRCloud", "confidence": "confirmed"}
    ],
    "keywords": [
      {"keyword": "听歌识曲", "confidence": "confirmed", "note": "feature label"},
      {"keyword": "听歌识曲算法", "confidence": "confirmed", "note": "algorithm setting"}
    ],
    "capture": ["AudioRecord", "MediaProjection", "MediaRecorder"],
    "egress": ["HttpURLConnection", "Socket"],
    "permissions": ["android.permission.RECORD_AUDIO", "android.permission.INTERNET"],
    "evidence": {
      "sdk_package": false, "native_lib": true, "acr_endpoint": true,
      "capture_and_egress": true, "cjk_keyword": true
    }
  }
}
```

The `evidence` block is a quick five-way summary; the `vendors`,
`native_libs`, `endpoints`, and `keywords` arrays give the specific items
behind each. Every matched item carries its own `confidence` (`confirmed` =
verified against a real APK during seeding; `likely`/`seed` = plausible but
unverified — see the vocabulary README).

Filtering a corpus for confident ACR:

```python
import json

records = [json.loads(l) for l in open("results/all_acr.jsonl")]
acr_apps = [r for r in records if r["acr"]["confidence"] in ("high", "medium")]
```

## Validation: what the grades mean in practice

The workflow was validated against three real Chinese-market music apps.
Two are genuine ACR; one is the negative control that proves the grading
does not over-claim.

| App | Grade | Evidence |
|-----|-------|----------|
| **NetEase Cloud Music** (`com.netease.cloudmusic`) | `high` | three fingerprint libraries, three capture APIs, `听歌识曲算法` and other implementation strings, egress — everything but a named SDK |
| **QQ Music** (`com.tencent.qqmusic`) | `high` | `libfingerprint_jni.so`, `MediaRecorder`, `听歌识曲` implementation strings |
| **畅听音乐** (`trend.cloudmusic.online`) | `none` | contains the string `听歌识曲榜` (a *chart named after the feature*) but **no** `RECORD_AUDIO`, no capture API, no fingerprint library — the keyword is inert |

The third app is the point: same keyword as the other two, opposite verdict,
because the model weighs capability, not vocabulary.

## Extending the vocabulary

The vendor knowledge is data, not code, in two CSVs under
`cim_app_histories/acr/`:

- **`acr_sdks.csv`** — SDK package signatures (`signature,vendor,product,
  category,region,confidence`).
- **`acr_signatures.csv`** — native-library, endpoint-path, and CJK-keyword
  patterns (`kind,pattern,vendor,note,confidence`).

Add a row to extend coverage; no code change. When you run against a real
app that a `likely`/`seed` entry was guessing at, promote it to `confirmed`
and add any new strings you see. The README in that folder documents the
provenance of every seeded entry and the known gaps (notably: non-Western
vendors, and apps that embed ACR second-hand rather than being music apps).

## Cost

`acr` parses the app's DEX files once and runs all detectors on that single
pass. On a large app (NetEase, 246 MB, 22 DEX files, ~1.1M strings) this is
around 160 seconds; small apps are a few seconds. The cost is the DEX parse,
which is unavoidable for string- and class-level detection.

## Limitations

- **The SDK internals are invisible.** The fingerprint pipeline
  (spectrogram → fingerprint → query) runs inside the SDK at runtime. Static
  analysis sees that an ACR SDK is *present* and that capture and network
  APIs *exist*; it does not see the transform between them. The workflow
  reports "ACR capability present", never "the app computed a fingerprint
  and sent it".
- **Seed vocabulary.** The CSVs are curated, not exhaustive. Absence of a
  signal is not proof of absence of ACR — only that no *known* signal fired.
  Non-Western vendors beyond ACRCloud/NetEase/QQ are a known gap.
- **Endpoint paths are heuristic.** `/identify` is used by plenty of non-ACR
  services; that is why a path alone never reaches `high`.
- **Obfuscation.** Package names can be shaded; native-library filenames and
  vendor hosts survive more often. Under-reporting is the safe failure — the
  workflow claims less than the truth, never more.

## See also

- [Working with results](results.md) — loading JSONL into pandas
- [CLI reference](cli.md) — all flags and batching options
- `cim_app_histories/acr/README.md` — the vocabulary and its provenance
