# Listening: tracing audio inputs and their parameters

The `listening` workflow is built for machine-listening studies. Where
`flows` asks "what inputs feed what modules" across all modalities,
`listening` asks the audio question in depth: how does this app capture
sound, what does it do to the signal, what does a model receive, and
what leaves the device — and crucially, *with what parameters*, and how
those parameters change along the way.

```bash
cim-apps listening --apk app.apk --outdir results/
cim-apps listening --apk-dir apps/ --outdir results/
```

Output is one pretty-printed JSON file per app
(`<app>.listening.json`), unlike the JSONL of the other workflows —
each app's trace is a single document meant to be read and visualised
as a whole. All the usual batching options (`--apk-dir`, `--apk-list`,
sharding, resume) work identically.

## The stage model

Audio processing in apps follows a recognisable pipeline, and the
workflow organises everything it finds into that canonical order:

```
capture  ->  dsp  ->  features  ->  inference  ->  output
```

**capture** is where sound enters: AudioRecord/AAudio/OpenSL for the
microphone, a stream player for network audio, MediaExtractor for
files, MIDI over Bluetooth. **dsp** covers signal conditioning —
resampling, denoising, echo cancellation, gain control, voice activity
detection, loudness normalisation. **features** is the transform into
model food: FFT/STFT, mel spectrograms, MFCCs, filterbanks, pitch and
chroma. **inference** is the model itself, with a task label
(speech_to_text, wake_word, speaker_recognition, music_analysis,
speech_synthesis, audio_classification, audio_embedding) and, where a
model file is referenced by name from an audio module, the model
artefact with its format. **output** is what leaves: transcripts and
labels, and network endpoints with their categories (upload, streaming,
recommendation).

A single native library frequently spans several stages — one `.so`
doing capture, DSP, and features is common — so chain entries are
per-(module, stage), each carrying the operations observed and the
parameters visible at that point.

## Parameters and transitions

For each stage the workflow extracts the audio parameter vocabulary
visible in the module's strings: sample rates (validated against the
standard set — 8000/16000/22050/44100/48000 etc., including "16k"
forms), channel layout (mono/stereo), named values such as `n_fft`,
`hop_length`, `frame_size`, `n_mels`, `buffer_size` and `bitrate`, and
codecs (Opus, AAC, PCM, FLAC...).

Where the *same parameter* appears with *different values* in
successive stages, a transition is recorded:

```json
{"parameter": "sample_rate",
 "from_stage": "capture",  "from": [48000],
 "to_stage":   "features", "to":   [16000]}
```

That particular transition — high-rate stereo capture collapsing to
16 kHz mono before features — is the classic signature of an ASR front
end, and it is exactly the kind of finding the workflow exists to
surface: not just *that* an app listens, but the shape of the listening.

## Two worked examples

These illustrate what the output shows for the two motivating cases.
They are schematic — what the workflow surfaces depends on what each
real app's binaries reveal, and the examples below are illustrative
shapes, not results from the named services.

**A speech-to-text app.** Sources show `microphone` evidenced by the
AudioRecord API, microphone keywords (including 麦克风), and the
RECORD_AUDIO permission as corroboration. The chain shows capture at
48 kHz stereo with a 3840-byte buffer; a dsp stage with resample,
denoise, and VAD; a features stage at 16 kHz mono with `n_fft 512`,
`hop_length 160`, `n_mels 80` (a standard log-mel front end); an
inference stage linking `assets/asr_v3.tflite` (task: speech_to_text)
referenced by the feature library; and an output stage with a
transcript and an upload endpoint. Two transitions are recorded:
sample_rate 48000→16000 and channel_layout stereo→mono.

**A music-streaming app with recommendations.** Sources show
`network_stream` (HLS/ExoPlayer evidence) rather than the microphone —
and, importantly, *no* microphone claim is invented just because the
app plays audio. The chain shows codec parameters (Opus/AAC) at
capture, loudness handling in dsp, then analysis features — tempo,
beat tracking, chroma — feeding an inference stage with task
music_analysis and an embedding vocabulary, and an output stage whose
endpoint is categorised recommendation (`.../recommendations/next`).
That is the observable skeleton of "what to play next": which signal
properties the app computes on-device, and where they are sent.

## Reading the output

```python
import json
rec = json.load(open("results/MyApp.listening.json"))

rec["summary"]            # sources, stages present, tasks, endpoints
rec["sources"]            # per-source: which modules, with what evidence
rec["chain"]              # the ordered stage entries
rec["parameter_transitions"]
```

Across a corpus, the summaries aggregate naturally — for instance,
counting which inference tasks co-occur with which sources, or how
common the 48 kHz→16 kHz signature is per app category.

## What this evidence is, and is not

The workflow performs static analysis: parameters are *vocabulary
observed in binary strings*, not measured runtime values. A `16000`
adjacent to `sample_rate` is strong evidence of a 16 kHz path; it is
not a recording of one, and a value may be a default, one of several
configurations, or occasionally an unrelated constant (the extractor
only accepts numbers that match known rates or named parameters, but
audit a sample by hand before reporting). Transitions are inferred from
stage co-location within the app, not from observed dataflow — the
`--trace`-style dex confirmation available in `flows` is a natural
extension here. Sources require co-located evidence and permissions
only corroborate, so an app is never claimed to use the microphone
merely because it could. Keyword tables carry English and Chinese and
are data, not code: extend them in
`src/cim_app_histories/calls/listening.py` (`STAGE_OPERATIONS`,
`INFERENCE_TASKS`, the parameter patterns) as your corpus teaches you
vendor-specific vocabulary.
