"""
Tests for the multi-modality staged chain in the flows workflow:
per-modality capture -> preprocess -> features -> inference -> output,
with stage-attributed parameters and detected transitions.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.multimodal_pipeline import build_flow_graph
from cim_app_histories.calls.stages import STAGE_ORDER


def so(strings, pad=120000):
    return b"\x00".join(s.encode() if isinstance(s, str) else s
                        for s in strings) + b"\x00" * pad


AUDIO_LIB = ("lib/arm64/libaudio.so", so([
    "AudioRecord", "android/media/audiorecord", "\u9ea6\u514b\u98ce",
    "sample_rate=48000", "stereo",
    "x" * 400, "resample", "denoise", "vad",
    "x" * 400, "log_mel", "fbank", "sample_rate=16000", "mono", "n_mels 80",
    "x" * 400, "asr", "speech_to_text", "transcript"]))

VIDEO_LIB = ("lib/arm64/libvideo.so", so([
    "camera2", "android/hardware/camera", "\u6444\u50cf\u5934",
    "1920x1080", "preview_frame",
    "x" * 400, "decode", "yuv", "scale_frame", "640x480",
    "x" * 400, "optical_flow",
    "x" * 400, "face_detect",
    "x" * 400, "render"]))

MODEL = ("assets/asr.tflite", b"\x18\x00\x00\x00TFL3" + b"\x00" * 70000)
PERMS = ["android.permission.RECORD_AUDIO", "android.permission.CAMERA",
         "android.permission.INTERNET"]


@pytest.fixture(scope="module")
def graph():
    return build_flow_graph(
        [AUDIO_LIB, VIDEO_LIB, MODEL], permissions=PERMS,
        dex_urls=["https://api.example.net/v1/upload/audio"])


def entries(graph, modality):
    return [e for e in graph["chain"] if e.get("modality") == modality]


def test_separate_chain_per_modality(graph):
    """Audio and video each get their own capture->...->output chain."""
    assert "audio" in graph["summary"]["modalities"]
    assert "video" in graph["summary"]["modalities"]
    audio_stages = [e["stage"] for e in entries(graph, "audio") if e.get("operations")]
    video_stages = [e["stage"] for e in entries(graph, "video") if e.get("operations")]
    for stages in (audio_stages, video_stages):
        assert "capture" in stages and "inference" in stages
        # chain follows canonical order
        idx = [STAGE_ORDER.index(s) for s in stages]
        assert idx == sorted(idx)


def test_operations_are_data_not_nodes(graph):
    """Stage operations live on chain entries; they never become graph
    nodes (no node-per-method explosion)."""
    node_ids = {n["id"] for n in graph["nodes"]}
    for e in graph["chain"]:
        for op in e.get("operations", []):
            assert op not in node_ids


def test_parameters_attached_per_stage(graph):
    cap = [e for e in entries(graph, "audio")
           if e["stage"] == "capture" and e.get("operations")][0]
    assert 48000 in cap["parameters"]["sample_rate"]
    assert "stereo" in cap["parameters"]["channel_layout"]
    feat = [e for e in entries(graph, "audio")
            if e["stage"] == "features" and e.get("operations")][0]
    assert feat["parameters"]["sample_rate"] == [16000]
    assert feat["parameters"]["n_mels"] == [80]


def test_parameter_transitions_detected(graph):
    """The resample-for-inference signature must surface as a transition."""
    ts = graph["parameter_transitions"]
    assert any(t["modality"] == "audio" and t["parameter"] == "sample_rate"
               and 48000 in t["from"] for t in ts)
    assert any(t["modality"] == "video" and t["parameter"] == "resolution"
               for t in ts)


def test_video_resolution_downscale_transition(graph):
    ts = [t for t in graph["parameter_transitions"]
          if t["modality"] == "video" and t["parameter"] == "resolution"]
    assert any("1920x1080" in t["from"] for t in ts)


def test_models_and_endpoints_in_chain(graph):
    models = [e for e in graph["chain"] if e.get("model")]
    assert any("asr.tflite" in m["model"] for m in models)
    eps = [e for e in graph["chain"] if e.get("endpoint")]
    assert any("api.example.net" in e["endpoint"] for e in eps)
    assert all(e["stage"] == "output" for e in eps)


def test_graph_nodes_links_preserved(graph):
    """The node/link graph the viewers consume is unchanged."""
    assert graph["nodes"] and graph["links"]
    assert any(l["kind"] == "feeds" for l in graph["links"])


# --- modality reconciliation and parameter scoping -------------------
def test_vision_and_nlp_map_to_canonical_modalities():
    """ClassifyModel labels models audio/vision/nlp; the stage vocabulary
    uses audio/image/text. One canonical set, so an app never reports
    both 'vision' and 'image' as if they were different things."""
    from cim_app_histories.calls.stages import canonical_modality
    assert canonical_modality("vision") == "image"
    assert canonical_modality("nlp") == "text"
    assert canonical_modality("audio") == "audio"
    assert canonical_modality("image") == "image"
    assert canonical_modality(None) == "unknown"


def test_model_entries_use_canonical_modality():
    face = ("assets/model/ttfacemodel/tt_face_v11.1.model", b"\x00" * 50000)
    lib = ("lib/arm64/libface.so", so(["face_detect", "tt_face_v11.1.model",
                                        "camera2", "preview_frame"]))
    g = build_flow_graph([lib, face], permissions=["android.permission.CAMERA"])
    assert "vision" not in g["summary"]["modalities"]
    models = [e for e in g["chain"] if e.get("model")]
    assert models and all(e["modality"] != "vision" for e in models)


def test_location_does_not_inherit_media_parameters():
    """A WebView library holds location APIs AND a media stack. Location
    stages must not report sample_rate/fps/bitrate/codecs borrowed from
    the media code (TikTok reported sample_rate=384, codecs=aac)."""
    webview = ("lib/arm64/libwebview.so", so([
        "fusedlocation", "geolocation", "locationmanager", "geofence",
        "kalman", "dwell", "trajectory", "coordinates",
        "aac", "h264", "opus", "fps=24", "bitrate=30000",
        "sample_rate=384", "sample_rate=44100"]))
    g = build_flow_graph([webview],
                         permissions=["android.permission.ACCESS_FINE_LOCATION"])
    loc = [e for e in g["chain"] if e.get("modality") == "location"]
    assert loc, "expected location stages"
    for e in loc:
        p = e.get("parameters", {})
        assert "sample_rate" not in p
        assert "fps" not in p
        assert "bitrate" not in p
        assert "codecs" not in p


def test_parameters_scoped_to_modality():
    from cim_app_histories.calls.stages import extract_parameters
    media = "aac h264 fps=24 bitrate=30000 sample_rate=44100 1920x1080"
    assert extract_parameters(media, "location") == {}
    audio = extract_parameters(media, "audio")
    assert "sample_rate" in audio and "resolution" not in audio
    video = extract_parameters(media, "video")
    assert "fps" in video and "resolution" in video
    assert "sample_rate" not in video


def test_no_module_wide_parameter_fallback():
    """A stage with no parameters near its own operations reports none,
    rather than borrowing the binary's unrelated numbers."""
    lib = ("lib/arm64/libmixed.so", so(
        ["locationmanager", "geofence"] + ["x" * 500] +
        ["sample_rate=48000", "mono", "audiorecord", "resample"]))
    g = build_flow_graph([lib], permissions=[])
    loc = [e for e in g["chain"] if e.get("modality") == "location"]
    for e in loc:
        assert not e.get("parameters")


# --- Bluetooth audio devices (mics, headsets, speakers) --------------
def test_bluetooth_audio_is_a_distinct_input():
    """bluetooth_audio (mics/headsets/speakers) is separate from
    bluetooth_midi (musical instruments): different research objects."""
    from cim_app_histories.calls.multimodal_pipeline import INPUT_SIGNATURES
    assert "bluetooth_audio" in INPUT_SIGNATURES
    assert "bluetooth_midi" in INPUT_SIGNATURES
    # the bare word "bluetooth" must not be a MIDI keyword any more:
    # it matched every library mentioning the radio
    assert "bluetooth" not in INPUT_SIGNATURES["bluetooth_midi"]["keywords"]


def test_bluetooth_mic_capture_detected_with_sco_profile():
    """A recorder capturing from a BT headset (Plaud-shaped) must show
    bluetooth_audio as an input and SCO routing at the capture stage."""
    lib = ("lib/arm64/libaudio.so", so([
        "android/bluetooth/bluetoothheadset", "bluetoothheadset",
        "startbluetoothsco", "setcommunicationdevice",
        "sample_rate=16000", "mono", "msbc", "audiorecord",
        "x" * 400, "resample", "denoise", "vad",
        "x" * 400, "log_mel", "n_mels 80",
        "x" * 400, "asr", "speech_to_text", "transcript"]))
    g = build_flow_graph([lib], permissions=[
        "android.permission.RECORD_AUDIO",
        "android.permission.BLUETOOTH_CONNECT",
        "android.permission.MODIFY_AUDIO_SETTINGS"])
    assert "bluetooth_audio" in g["summary"]["inputs"]
    cap = [e for e in g["chain"]
           if e.get("modality") == "audio" and e.get("stage") == "capture"]
    assert cap, "expected an audio capture stage"
    p = cap[0].get("parameters", {})
    assert p.get("bt_profile") == ["sco"]      # microphone-capable channel
    assert "msbc" in p.get("bt_codecs", [])


def test_bluetooth_speaker_playback_does_not_claim_capture():
    """An app that only plays TO a BT speaker (A2DP) must not be shown
    capturing from it: A2DP carries no microphone."""
    lib = ("lib/arm64/libplayer.so", so([
        "bluetootha2dp", "a2dp", "ldac", "aptx", "exoplayer",
        "44100", "stereo", "x" * 400, "loudness",
        "x" * 400, "playlist", "next_track"]))
    g = build_flow_graph([lib],
                         permissions=["android.permission.BLUETOOTH_CONNECT"])
    assert not any(e.get("stage") == "capture" for e in g["chain"])
    out = [e for e in g["chain"]
           if e.get("modality") == "audio" and e.get("stage") == "output"]
    assert out and out[0]["parameters"]["bt_profile"] == ["a2dp"]


def test_bt_profile_distinguishes_sco_from_a2dp():
    from cim_app_histories.calls.stages import extract_parameters
    sco = extract_parameters("startbluetoothsco audiorecord 16000 mono", "audio")
    assert sco["bt_profile"] == ["sco"]
    a2dp = extract_parameters("bluetootha2dp ldac 44100 stereo", "audio")
    assert a2dp["bt_profile"] == ["a2dp"]


def test_bluetooth_params_scoped_to_audio_only():
    from cim_app_histories.calls.stages import extract_parameters
    txt = "startbluetoothsco ldac locationmanager"
    assert "bt_profile" not in extract_parameters(txt, "location")
    assert "bt_profile" in extract_parameters(txt, "audio")


# --- Bluetooth companion devices (BLE/GATT hardware) -----------------
def test_bluetooth_device_is_a_distinct_input():
    """bluetooth_device (BLE/GATT/RFCOMM companion hardware) is separate
    from bluetooth_audio (an SCO/A2DP route): purpose-built hardware
    streams over a data link, which is not an audio route."""
    from cim_app_histories.calls.multimodal_pipeline import INPUT_SIGNATURES
    assert "bluetooth_device" in INPUT_SIGNATURES
    sig = INPUT_SIGNATURES["bluetooth_device"]
    assert "bluetoothgatt" in sig["keywords"]
    assert "android.permission.BLUETOOTH_SCAN" in sig["permissions"]


def test_companion_recorder_shows_link_then_audio_chain():
    """The Plaud shape: a companion recorder pairs, moves the recording
    over GATT, and only then is the audio processed. Both chains must be
    present and distinct -- that two-step is the finding."""
    link = ("lib/arm64/libdevicelink.so", so([
        "BluetoothLeScanner", "startScan", "companiondevicemanager", "pairing",
        "x" * 400, "connectGatt", "bluetoothgatt", "gattcharacteristic",
        "x" * 400, "chunk_transfer", "opus_frame", "sbc_decode",
        "x" * 400, "file_received", "recording_download", "sync_complete"]))
    asr = ("lib/arm64/libasr.so", so([
        "audiorecord", "sample_rate=16000", "mono",
        "x" * 400, "resample", "denoise", "vad",
        "x" * 400, "log_mel", "n_mels 80",
        "x" * 400, "asr", "speech_to_text", "transcript"]))
    g = build_flow_graph([link, asr], permissions=[
        "android.permission.BLUETOOTH_CONNECT",
        "android.permission.BLUETOOTH_SCAN",
        "android.permission.RECORD_AUDIO"])

    assert "bluetooth_device" in g["summary"]["inputs"]
    assert "bluetooth" in g["summary"]["modalities"]
    assert "audio" in g["summary"]["modalities"]

    bt = [e["stage"] for e in g["chain"]
          if e.get("modality") == "bluetooth" and e.get("operations")]
    assert "capture" in bt            # discovery/pairing
    assert "output" in bt             # recording received
    audio = [e["stage"] for e in g["chain"]
             if e.get("modality") == "audio" and e.get("operations")]
    assert "inference" in audio       # ...then transcribed


def test_bluetooth_device_chain_is_not_audio_modality():
    """A GATT link is a transfer path, not an audio route: it must not be
    folded into the audio chain, or the two-step disappears."""
    link = ("lib/arm64/libdevicelink.so", so([
        "bluetoothgatt", "connectGatt", "gattcharacteristic",
        "bluetoothlescanner", "startScan", "file_received"]))
    g = build_flow_graph([link],
                         permissions=["android.permission.BLUETOOTH_SCAN"])
    bt_entries = [e for e in g["chain"] if e.get("modality") == "bluetooth"]
    assert bt_entries, "expected a bluetooth chain"


# --- regressions from the old single bluetooth_midi input ------------
def test_bare_bluetooth_keyword_does_not_create_midi_link():
    """Regression: 'bluetooth_midi' used to match the bare word
    'bluetooth', so a live-casting library was reported as a MIDI input
    (TikTok: libdex_df_live_cast.so linked on that single keyword)."""
    lib = ("lib/arm64/liblivecast.so", so(["bluetooth", "rtmp", "encode"]))
    g = build_flow_graph([lib], permissions=[
        "android.permission.BLUETOOTH", "android.permission.BLUETOOTH_CONNECT"])
    assert not [i for i in g["summary"]["inputs"] if i.startswith("bluetooth")]


def test_bare_midi_keyword_does_not_create_midi_link():
    """Regression: an audio-effects library was linked as a MIDI input on
    the single keyword 'midi' (TikTok: libaudioeffect.so)."""
    lib = ("lib/arm64/libaudioeffect.so", so(["midi", "reverb", "equalizer"]))
    g = build_flow_graph([lib], permissions=[
        "android.permission.BLUETOOTH", "android.permission.BLUETOOTH_CONNECT"])
    assert "bluetooth_midi" not in g["summary"]["inputs"]


def test_real_midi_instrument_still_detected():
    """The split must not lose genuine MIDI: instruments and controllers
    remain a distinct research object."""
    lib = ("lib/arm64/libmidi.so", so([
        "midimanager", "mididevice", "midiinputport", "midioutputport",
        "ble_midi"]))
    g = build_flow_graph([lib],
                         permissions=["android.permission.BLUETOOTH_CONNECT"])
    assert "bluetooth_midi" in g["summary"]["inputs"]


def test_bt_route_facts_apply_to_whole_chain():
    """bt_profile/bt_codecs characterise the LINK, not one stage: a
    library speaking A2DP speaks it for the whole path, wherever the
    string sits. (Values that genuinely change along the chain, like
    sample_rate, stay proximity-attributed.)"""
    lib = ("lib/arm64/libplayer.so", so([
        "bluetootha2dp", "ldac", "44100", "stereo",
        "x" * 500, "loudness", "x" * 500, "playlist", "next_track"]))
    g = build_flow_graph([lib],
                         permissions=["android.permission.BLUETOOTH_CONNECT"])
    audio = [e for e in g["chain"]
             if e.get("modality") == "audio" and e.get("parameters")]
    assert audio, "expected audio stages with parameters"
    for e in audio:
        assert e["parameters"].get("bt_profile") == ["a2dp"]