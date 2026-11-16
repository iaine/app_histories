"""
Tracker network call graph: the shared tracker table, the per-app graph
builder, the corpus merge and the GraphML export.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.trackers import (       # noqa: E402
    tracker_list, build_tracker_graph, merge_network_records, write_graphml)


# ---- DEX doubles (no androguard needed) ------------------------------
class _Ins:
    def __init__(self, name, output):
        self._n, self._o = name, output

    def get_name(self): return self._n
    def get_output(self): return self._o


class _Code:
    def __init__(self, ins): self._ins = ins
    def get_bc(self): return self
    def get_instructions(self): return self._ins


class _Method:
    def __init__(self, cls, name, calls, desc="()V"):
        self._cls, self._name, self._desc = cls, name, desc
        self._code = None if calls is None else _Code(
            [_Ins("invoke-virtual", f"v0, {c}") for c in calls])

    def get_class_name(self): return self._cls
    def get_name(self): return self._name
    def get_descriptor(self): return self._desc
    def get_code(self): return self._code


class _Dex:
    def __init__(self, methods): self._m = methods
    def get_encoded_methods(self): return self._m


TRACKERS = {"com.appsflyer": {"name": "AppsFlyer", "category": "analytics"},
            "com.split": {"name": "Split", "category": "ab"}}
NET = ("Ljava/net/HttpURLConnection", "Lokhttp3/")

APP = "Lcom/demo/Main;"
AF = "Lcom/appsflyer/AppsFlyerLib;"
AF2 = "Lcom/appsflyer/internal/Sender;"


def demo_dex():
    return _Dex([
        _Method(APP, "onCreate", [f"{AF}->start()V",
                                  "Landroid/util/Log;->d()I"]),
        _Method(AF, "start", [f"{AF2}->send()V"]),
        _Method(AF2, "send", ["Ljava/net/HttpURLConnection;->connect()V",
                              "Ljava/lang/String;->length()I",
                              f"{APP}->callback()V"]),
        _Method(APP, "callback", []),
        _Method(APP, "helper", ["Ljava/lang/String;->length()I"]),
    ])


def by_id(graph):
    return {n["id"]: n for n in graph["nodes"]}


def link_set(graph):
    return {(l["source"], l["target"], l["kind"]) for l in graph["links"]}


# ---- tracker table ---------------------------------------------------
def test_tracker_list_is_the_union_across_metadata_files(tmp_path):
    def meta(name, trackers):
        (tmp_path / name).write_text(json.dumps({"trackers": trackers}) + "\n")

    meta("a.metadata.jsonl", [
        {"signature": "com.appsflyer", "name": "AppsFlyer", "category": "analytics"}])
    meta("b.metadata.jsonl", [
        {"signature": "com.appsflyer", "name": "AppsFlyer", "category": "analytics"},
        {"signature": "com.braze", "name": "Braze", "category": "analytics"}])
    meta("c.flows.jsonl", [
        {"signature": "com.ignored", "name": "x", "category": "x"}])

    trackers = tracker_list(tmp_path)
    assert list(trackers) == ["com.appsflyer", "com.braze"]      # sorted, deduped
    assert trackers["com.braze"]["category"] == "analytics"


def test_tracker_list_survives_blank_and_truncated_lines(tmp_path):
    (tmp_path / "a.metadata.jsonl").write_text(
        "\n" + json.dumps({"trackers": [{"signature": "com.braze"}]})
        + "\n{\"trackers\": [{\"signa\n")
    assert list(tracker_list(tmp_path)) == ["com.braze"]


def test_tracker_list_missing_directory_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        tracker_list(tmp_path / "nope")


# ---- graph builder ---------------------------------------------------
def test_edges_into_and_out_of_a_tracker_are_kept():
    g = build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET)
    links = link_set(g)
    assert (f"{APP}->onCreate()V", f"{AF}->start()V", "calls_tracker") in links
    assert (f"{AF2}->send()V", "Ljava/net/HttpURLConnection;->connect()V",
            "network") in links
    assert (f"{AF2}->send()V", "Ljava/lang/String;->length()I",
            "tracker_calls") in links


def test_calls_unrelated_to_any_tracker_are_dropped():
    g = build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET)
    ids = by_id(g)
    assert "Landroid/util/Log;->d()I" not in ids        # app -> framework
    assert f"{APP}->helper()V" not in ids               # never touches a tracker


def test_calls_inside_one_tracker_are_opt_in():
    internal = (f"{AF}->start()V", f"{AF2}->send()V", "internal")
    assert internal not in link_set(
        build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET))
    assert internal in link_set(
        build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET,
                            include_internal=True))


def test_node_kinds():
    ids = by_id(build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET))
    assert ids[f"{AF}->start()V"]["kind"] == "tracker"
    assert ids[f"{AF}->start()V"]["tracker"] == "com.appsflyer"
    assert ids[f"{AF}->start()V"]["category"] == "analytics"
    assert ids["Ljava/net/HttpURLConnection;->connect()V"]["kind"] == "network_api"
    assert ids["Ljava/lang/String;->length()I"]["kind"] == "external"
    assert ids[f"{APP}->onCreate()V"]["kind"] == "app"


def test_callback_into_app_code_is_app_not_external():
    """A tracker calling back into a class the APK ships is 'app', even
    though it is first met as a callee."""
    ids = by_id(build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET))
    assert ids[f"{APP}->callback()V"]["kind"] == "app"


def test_callee_defined_in_a_later_dex_is_still_app():
    first = _Dex([_Method(AF, "start", ["Lcom/demo/Late;->run()V"])])
    second = _Dex([_Method("Lcom/demo/Late;", "run", [])])
    ids = by_id(build_tracker_graph([first, second], TRACKERS))
    assert ids["Lcom/demo/Late;->run()V"]["kind"] == "app"


def test_signature_match_is_anchored():
    """com.split must not claim com.splitties (the substring bug the
    tracker detector already guards against)."""
    dex = _Dex([_Method(APP, "go", ["Lcom/splitties/Toast;->show()V",
                                    "Lcom/split/Client;->get()V"])])
    ids = by_id(build_tracker_graph([dex], TRACKERS))
    assert "Lcom/splitties/Toast;->show()V" not in ids
    assert ids["Lcom/split/Client;->get()V"]["tracker"] == "com.split"


def test_repeated_call_sites_add_weight_not_edges():
    dex = _Dex([_Method(APP, "go", [f"{AF}->start()V"] * 3)])
    g = build_tracker_graph([dex], TRACKERS)
    assert len(g["links"]) == 1 and g["links"][0]["weight"] == 3


def test_non_invoke_instructions_are_ignored():
    m = _Method(APP, "go", [])
    m._code = _Code([_Ins("const-string", f"v0, '{AF}->start()V'")])
    assert build_tracker_graph([_Dex([m])], TRACKERS)["links"] == []


def test_class_level_collapses_methods():
    g = build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET,
                            level="class")
    ids = by_id(g)
    assert set(ids) == {APP, AF, AF2, "Ljava/net/HttpURLConnection;",
                        "Ljava/lang/String;"}
    assert (APP, AF, "calls_tracker") in link_set(g)


def test_abstract_methods_and_bad_methods_do_not_stop_the_scan():
    class Broken(_Method):
        def get_code(self): raise RuntimeError("undecodable")

    dex = _Dex([_Method(APP, "abstract", None), Broken(APP, "bad", []),
                _Method(APP, "go", [f"{AF}->start()V"])])
    assert len(build_tracker_graph([dex], TRACKERS)["links"]) == 1


def test_summary_counts():
    s = build_tracker_graph([demo_dex()], TRACKERS, network_apis=NET)["summary"]
    assert s["trackers_found"] == ["com.appsflyer"]
    assert s["trackers_searched"] == 2
    assert s["network_apis_reached"] == ["Ljava/net/HttpURLConnection;"]
    assert s["nodes"] == sum(s["node_kinds"].values())


# ---- merge + GraphML -------------------------------------------------
def write_record(path, pkg, graph):
    for n in graph["nodes"]:
        n["pkg"] = pkg
    path.write_text(json.dumps(
        {"pkg": pkg, "version": "1.0",
         "graph": {"nodes": graph["nodes"], "links": graph["links"]}}) + "\n")


def two_app_corpus(tmp_path):
    for pkg in ("com.one", "com.two"):
        write_record(tmp_path / f"{pkg}.network.jsonl", pkg,
                     build_tracker_graph([demo_dex()], TRACKERS,
                                         network_apis=NET))
    return sorted(tmp_path.glob("*.network.jsonl"))


def test_merge_shares_trackers_and_separates_app_code(tmp_path):
    nodes, edges, apps = merge_network_records(two_app_corpus(tmp_path))
    assert [a["pkg"] for a in apps] == ["com.one", "com.two"]
    # the same SDK method in both apps is one node, seen twice
    assert nodes[f"{AF}->start()V"]["apps"] == 2
    # identical app class names stay apart
    assert f"com.one::{APP}->onCreate()V" in nodes
    assert f"com.two::{APP}->onCreate()V" in nodes
    assert nodes[f"com.one::{APP}->onCreate()V"]["pkg"] == "com.one"
    # the shared tracker -> network edge accumulates
    e = edges[(f"{AF2}->send()V", "Ljava/net/HttpURLConnection;->connect()V")]
    assert e["apps"] == 2 and e["weight"] == 2


def test_graphml_round_trip(tmp_path):
    nx = pytest.importorskip("networkx")
    nodes, edges, _ = merge_network_records(two_app_corpus(tmp_path))
    out = tmp_path / "graph" / "network.graphml"
    n_nodes, n_edges = write_graphml(nodes, edges, out)
    g = nx.read_graphml(out)
    assert g.is_directed()
    assert (g.number_of_nodes(), g.number_of_edges()) == (n_nodes, n_edges)
    assert g.nodes[f"{AF}->start()V"]["tracker"] == "com.appsflyer"
    assert g.nodes[f"{AF}->start()V"]["apps"] == 2
    assert not list(out.parent.glob("*.tmp"))


def test_building_the_graph_does_not_import_networkx():
    """networkx is only for the final translation: the per-app scan must
    not pull it in (it runs in every worker)."""
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); "
            "from cim_app_histories.calls.trackers import build_tracker_graph; "
            "build_tracker_graph([], {}); "
            "assert 'networkx' not in sys.modules"
            % str(Path(__file__).resolve().parents[1] / "src"))
    subprocess.run([sys.executable, "-c", code], check=True)


# ---- CLI -------------------------------------------------------------
def test_cli_reads_trackers_once_and_writes_one_graphml(tmp_path, monkeypatch):
    from cim_app_histories import cli
    import cim_app_histories.calls.trackers as tr

    meta, apks, out = tmp_path / "meta", tmp_path / "apks", tmp_path / "out"
    meta.mkdir(); apks.mkdir()
    (meta / "x.metadata.jsonl").write_text(json.dumps({"trackers": [
        {"signature": "com.appsflyer", "name": "AppsFlyer",
         "category": "analytics"}]}) + "\n")
    for name in ("a.apk", "b.apk"):
        (apks / name).write_bytes(b"x")

    reads = []
    real = tr.tracker_list
    monkeypatch.setattr(tr, "tracker_list",
                        lambda d: reads.append(d) or real(d))

    seen = []

    def fake_analyse(apk_path, trackers, level="method",
                     include_internal=False):
        seen.append(sorted(trackers))
        g = build_tracker_graph([demo_dex()], trackers, network_apis=NET)
        pkg = Path(apk_path).stem
        return {"pkg": pkg, "version": "1",
                "graph": {"nodes": g["nodes"], "links": g["links"]},
                "summary": g["summary"]}

    monkeypatch.setattr(cli, "analyse_network", fake_analyse)

    rc = cli.main(["network", "--input-dir", str(meta), "--apk-dir", str(apks),
                   "--outdir", str(out), "--workers", "1"])
    assert rc == 0
    assert len(reads) == 1                       # metadata read once
    assert seen == [["com.appsflyer"]] * 2       # every APK gets the full set
    assert (out / "a.network.jsonl").exists() and (out / "b.network.jsonl").exists()
    assert len(list(out.glob("*.graphml"))) == 1 # ONE combined graph
    assert (out / "network.graphml").stat().st_size > 0


def test_cli_array_run_defers_the_graph_to_network_merge(tmp_path, monkeypatch):
    from cim_app_histories import cli

    meta, apks, out = tmp_path / "meta", tmp_path / "apks", tmp_path / "out"
    meta.mkdir(); apks.mkdir()
    (meta / "x.metadata.jsonl").write_text(json.dumps({"trackers": [
        {"signature": "com.appsflyer"}]}) + "\n")
    for name in ("a.apk", "b.apk"):
        (apks / name).write_bytes(b"x")

    def fake_analyse(apk_path, trackers, **_):
        g = build_tracker_graph([demo_dex()], trackers)
        return {"pkg": Path(apk_path).stem, "version": "1",
                "graph": {"nodes": g["nodes"], "links": g["links"]}}

    monkeypatch.setattr(cli, "analyse_network", fake_analyse)
    common = ["network", "--input-dir", str(meta), "--apk-dir", str(apks),
              "--outdir", str(out), "--workers", "1", "--task-count", "2"]
    for i in ("0", "1"):
        assert cli.main(common + ["--task-index", i]) == 0
    assert not list(out.glob("*.graphml"))       # no shard writes the graph

    assert cli.main(["network-merge", "--outdir", str(out)]) == 0
    assert (out / "network.graphml").exists()


def test_cli_refuses_to_run_without_any_trackers(tmp_path):
    from cim_app_histories import cli
    meta, apks = tmp_path / "meta", tmp_path / "apks"
    meta.mkdir(); apks.mkdir()
    (apks / "a.apk").write_bytes(b"x")
    with pytest.raises(SystemExit):
        cli.main(["network", "--input-dir", str(meta), "--apk-dir", str(apks),
                  "--outdir", str(tmp_path / "out")])
