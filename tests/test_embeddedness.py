"""
Tracker embeddedness per app, per era: computed from network records,
never from APKs.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.calls.embeddedness import (      # noqa: E402
    era_of, release_metrics, embeddedness_table, write_embeddedness_csv,
    iter_network_records, CSV_COLUMNS, METRICS)

AF, BR = "com.appsflyer", "com.braze"


def node(nid, kind, tracker=None):
    n = {"id": nid, "kind": kind, "class": nid.split("->")[0]}
    if tracker:
        n.update(tracker=tracker, category="analytics")
    return n


def link(s, t, kind, weight=1):
    return {"source": s, "target": t, "kind": kind, "weight": weight}


def record(version, code, callers=2, pkg="com.demo", with_braze=False,
           methods=1000):
    """An app with `callers` methods calling AppsFlyer, which reaches two
    network classes and calls back into the app once."""
    nodes = [node("Laf/Lib;->start()V", "tracker", AF),
             node("Laf/Net;->send()V", "tracker", AF),
             node("Ljava/net/HttpURLConnection;->connect()V", "network_api"),
             node("Lokhttp3/Call;->execute()V", "network_api"),
             node("Lapp/Cb;->done()V", "app"),
             node("Ljava/lang/String;->length()I", "external")]
    links = [link("Laf/Net;->send()V",
                  "Ljava/net/HttpURLConnection;->connect()V", "network", 3),
             link("Laf/Net;->send()V", "Lokhttp3/Call;->execute()V", "network"),
             link("Laf/Net;->send()V", "Lapp/Cb;->done()V", "tracker_calls"),
             link("Laf/Net;->send()V", "Ljava/lang/String;->length()I",
                  "tracker_calls", 9)]
    for i in range(callers):
        nodes.append(node(f"Lapp/C{i};->go()V", "app"))
        links.append(link(f"Lapp/C{i};->go()V", "Laf/Lib;->start()V",
                          "calls_tracker", 2))
    if with_braze:
        nodes.append(node("Lbr/Braze;->log()V", "tracker", BR))
        links.append(link("Laf/Lib;->start()V", "Lbr/Braze;->log()V",
                          "tracker_to_tracker"))
    return {"pkg": pkg, "version": version, "version_code": code,
            "graph": {"nodes": nodes, "links": links},
            "summary": {"level": "method", "methods_scanned": methods}}


# ---- eras ------------------------------------------------------------
@pytest.mark.parametrize("version,level,era", [
    ("3.103.0-6392", "major", "3.*"),
    ("3.103.0-6392", "minor", "3.103.*"),
    ("3.103.0-6392", "release", "3.103.0-6392"),
    ("43.7.3", "major", "43.*"),
    ("v2", "minor", "2.*"),              # no minor part to group on
    ("beta", "major", "unknown"),
    ("", "release", "unknown"),
    (None, "major", "unknown"),
])
def test_era_of(version, level, era):
    assert era_of(version, level) == era


def test_era_of_rejects_unknown_level():
    with pytest.raises(ValueError):
        era_of("1.0", "decade")


# ---- one release -----------------------------------------------------
def test_release_metrics_counts():
    m = release_metrics(record("1.0", 10, callers=3, with_braze=True))[AF]
    assert m["app_callers"] == 3
    assert m["call_sites"] == 6                  # 3 callers x weight 2
    assert m["entry_points"] == 1                # only Lib.start is called
    assert m["tracker_nodes"] == 2
    assert m["network_apis"] == 2
    assert m["network_call_sites"] == 4          # 3 + 1
    assert m["apk_code_called"] == 1
    assert m["other_trackers"] == 1
    assert set(METRICS) <= set(m)


def test_calls_to_the_framework_are_not_counted_as_network_or_callbacks():
    m = release_metrics(record("1.0", 10))[AF]
    assert m["network_call_sites"] == 4 and m["apk_code_called"] == 1


def test_a_tracker_only_called_by_another_tracker_still_appears():
    m = release_metrics(record("1.0", 10, with_braze=True))[BR]
    assert m["tracker_nodes"] == 1 and m["app_callers"] == 0


def test_a_tracker_calling_another_is_not_an_app_caller():
    """AppsFlyer -> Braze must not count AppsFlyer as app code."""
    assert release_metrics(record("1.0", 10, with_braze=True))[BR][
        "call_sites"] == 0


# ---- eras of releases ------------------------------------------------
def test_releases_are_grouped_by_major_version_and_averaged():
    rows = embeddedness_table([record("1.0", 10, callers=2),
                               record("1.5", 15, callers=4),
                               record("2.0", 20, callers=10)])
    assert [(r["era"], r["tracker"]) for r in rows] == [("1.*", AF), ("2.*", AF)]
    one, two = rows
    assert one["releases"] == 2 and one["app_callers"] == 3.0   # mean of 2, 4
    assert one["call_sites"] == 6.0                             # mean of 4, 8
    assert (one["first_version"], one["last_version"]) == ("1.0", "1.5")
    assert (one["first_version_code"], one["last_version_code"]) == (10, 15)
    assert two["releases"] == 1 and two["app_callers"] == 10.0


def test_minor_and_release_levels_split_further():
    recs = [record("1.0.1", 10), record("1.0.2", 11), record("1.5.0", 15)]
    assert [r["era"] for r in embeddedness_table(recs, "minor")] == \
        ["1.0.*", "1.5.*"]
    assert [r["era"] for r in embeddedness_table(recs, "release")] == \
        ["1.0.1", "1.0.2", "1.5.0"]


def test_presence_is_separate_from_depth():
    """A tracker in one of two releases is 50% present, and its counts
    are averaged over the release that has it, not halved."""
    rows = embeddedness_table([record("1.0", 10, with_braze=True),
                               record("1.1", 11, with_braze=False)])
    braze = next(r for r in rows if r["tracker"] == BR)
    assert braze["releases"] == 2 and braze["releases_present"] == 1
    assert braze["presence"] == 0.5
    assert braze["tracker_nodes"] == 1.0
    assert braze["first_version"] == braze["last_version"] == "1.0"


def test_apps_are_never_pooled_together():
    rows = embeddedness_table([record("1.0", 10, pkg="com.a", callers=1),
                               record("1.0", 10, pkg="com.b", callers=5)])
    assert [(r["pkg"], r["app_callers"]) for r in rows] == \
        [("com.a", 1.0), ("com.b", 5.0)]


def test_the_same_release_scanned_twice_counts_once():
    rows = embeddedness_table([record("1.0", 10), record("1.0", 10)])
    assert rows[0]["releases"] == 1


def test_eras_sort_numerically_not_alphabetically():
    rows = embeddedness_table([record("10.0", 100), record("9.0", 90),
                               record("2.0", 20)])
    assert [r["era"] for r in rows] == ["2.*", "9.*", "10.*"]


def test_caller_share_is_callers_over_methods_scanned():
    row = embeddedness_table([record("1.0", 10, callers=5, methods=1000)])[0]
    assert row["app_methods_scanned"] == 1000
    assert row["app_caller_share"] == 0.005


def test_caller_share_is_blank_at_class_level():
    rec = record("1.0", 10)
    rec["summary"]["level"] = "class"
    assert embeddedness_table([rec])[0]["app_caller_share"] is None


def test_records_without_version_code_or_summary_still_work():
    rec = record("1.0", 10)
    del rec["version_code"], rec["summary"]
    row = embeddedness_table([rec])[0]
    assert row["first_version_code"] is None
    assert row["app_methods_scanned"] is None and row["app_callers"] == 2.0


# ---- files -----------------------------------------------------------
def test_iter_skips_blank_broken_and_graphless_lines(tmp_path):
    p = tmp_path / "a.network.jsonl"
    p.write_text("\n" + json.dumps(record("1.0", 10)) + "\n{broken\n"
                 + json.dumps({"error": "boom"}) + "\n")
    assert len(list(iter_network_records([p]))) == 1


def test_csv_round_trip(tmp_path):
    rows = embeddedness_table([record("1.0", 10), record("2.0", 20)])
    out = tmp_path / "t" / "e.csv"
    assert write_embeddedness_csv(rows, out) == 2
    read = list(csv.DictReader(open(out)))
    assert list(read[0]) == CSV_COLUMNS
    assert read[0]["era"] == "1.*" and read[0]["app_callers"] == "2.0"
    assert not list(out.parent.glob("*.tmp"))


def test_cli_reads_results_only(tmp_path):
    from cim_app_histories import cli
    for i, (v, c) in enumerate([("1.0", 10), ("1.2", 12), ("2.0", 20)]):
        (tmp_path / f"r{i}.network.jsonl").write_text(
            json.dumps(record(v, c)) + "\n")
    assert cli.main(["network-embed", "--input-dir", str(tmp_path)]) == 0
    read = list(csv.DictReader(open(tmp_path / "network.embeddedness.csv")))
    assert [(r["era"], r["releases"]) for r in read] == [("1.*", "2"), ("2.*", "1")]

    out = tmp_path / "by_release.csv"
    assert cli.main(["network-embed", "--input-dir", str(tmp_path),
                     "--era", "release", "--csv", str(out)]) == 0
    assert len(list(csv.DictReader(open(out)))) == 3


def test_cli_with_no_network_files_fails_clearly(tmp_path):
    from cim_app_histories import cli
    assert cli.main(["network-embed", "--input-dir", str(tmp_path)]) == 1
