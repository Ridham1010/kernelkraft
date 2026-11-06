"""Stage 7 analysis tests (no QEMU). Uses only FAKE data."""

import csv
import math
from pathlib import Path

import pytest

from harness import analyze

FIELDS = ("policy", "cpus", "run", "alpha", "finish", "deadline", "miss",
          "status", "commit_hash", "rawlog_path")
FIXTURE = Path(__file__).resolve().parents[2] / "results" / "fixture_results.csv"


def row(policy, cpus, run, finish, deadline=37, miss=None, status="ok", alpha="1.5"):
    if status != "ok":
        finish = deadline = miss = ""
    elif miss is None:
        miss = 1 if finish > deadline else 0
    return {"policy": policy, "cpus": str(cpus), "run": str(run), "alpha": alpha,
            "finish": str(finish), "deadline": str(deadline), "miss": str(miss),
            "status": status, "commit_hash": "FAKE0000",
            "rawlog_path": "logs/FAKE/x.raw"}


def test_row_helper_and_fixture_use_plan_columns():
    assert tuple(row("rr", 1, 1, 40)) == FIELDS
    rows = analyze.read_rows(FIXTURE)
    assert tuple(rows[0]) == FIELDS
    assert {r["status"] for r in rows} == {"ok", "timeout", "no_result"}
    assert FIXTURE.read_text().startswith("# FAKE FIXTURE DATA")


def test_only_ok_rows_analysed_and_others_counted():
    rows = [row("rr", 1, 1, 40), row("rr", 1, 2, 30, status="bad_result"),
            row("rr", 1, 3, 30, status="success")]  # legacy status is not ok
    result = analyze.analyze(rows, 1.5)
    cell = result["summary"][0]
    assert cell["n"] == 1
    assert cell["dropped_statuses"] == "bad_result:1;success:1"


def test_drop_counting_per_cell():
    rows = [
        row("rr", 1, 1, 40), row("rr", 1, 2, 0, status="timeout"),
        row("rr", 1, 3, 0, status="timeout"), row("rr", 1, 4, 0, status="panic"),
        row("edf", 1, 1, 30),
    ]
    result = analyze.analyze(rows, 1.5)
    cells = {(r["policy"], r["cpus"]): r for r in result["summary"]}
    assert cells[("rr", 1)]["n"] == 1
    assert cells[("rr", 1)]["dropped"] == 3
    assert cells[("rr", 1)]["dropped_statuses"] == "panic:1;timeout:2"
    assert cells[("edf", 1)]["dropped"] == 0


def test_miss_recomputed_and_mismatch_reported():
    # finish 40 > deadline 37 but the miss column says 0: reported, recomputed.
    rows = [row("rr", 1, 1, 40, miss=0), row("rr", 1, 2, 30, miss=0)]
    result = analyze.analyze(rows, 1.5)
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["run"] == "1"
    assert result["mismatches"][0]["host_miss"] == 1
    assert result["summary"][0]["misses"] == 1


def test_finish_equal_to_deadline_is_not_a_miss():
    result = analyze.analyze([row("rr", 1, 1, 37)], 1.5)
    assert result["summary"][0]["misses"] == 0
    assert result["mismatches"] == []


def test_duplicates_reported_and_all_success_kept():
    rows = [row("edf", 1, 1, 30), row("edf", 1, 1, 40),
            row("edf", 1, 2, 0, status="no_result"), row("edf", 1, 2, 31)]
    result = analyze.analyze(rows, 1.5)
    assert len(result["duplicates"]) == 2
    flags = {d["key"][3]: d["multiple_ok"] for d in result["duplicates"]}
    assert flags == {1: True, 2: False}
    assert result["summary"][0]["n"] == 3


def test_unparseable_ok_row_is_reported():
    bad = row("rr", 1, 1, 40)
    bad["finish"] = ""
    result = analyze.analyze([bad], 1.5)
    assert len(result["unparseable"]) == 1


def test_bootstrap_deterministic_with_fixed_seed():
    outcomes = [1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 0, 1]
    first = analyze.bootstrap_ci(outcomes)
    second = analyze.bootstrap_ci(outcomes)
    assert first == second
    low, high = first
    assert 0.0 <= low <= sum(outcomes) / len(outcomes) <= high <= 1.0
    # Pinned regression value for this seed (percentiles of n=20 lie on a 0.05 grid).
    assert first == (0.25, 0.65)


def test_bootstrap_degenerate_cells():
    assert analyze.bootstrap_ci([0] * 10) == (0.0, 0.0)
    assert analyze.bootstrap_ci([1] * 10) == (1.0, 1.0)
    assert analyze.bootstrap_ci([]) == (None, None)


# Reference p-values from R fisher.test (two-sided).
@pytest.mark.parametrize("table, expected", [
    ([[3, 1], [1, 3]], 0.4857142857),
    ([[1, 9], [11, 3]], 0.002759456),
    ([[0, 10], [10, 0]], 2 / math.comb(20, 10)),
    ([[5, 5], [5, 5]], 1.0),
    ([[20, 0], [0, 20]], 2 / math.comb(40, 20)),
])
def test_manual_fisher_known_values(table, expected):
    assert analyze.fisher_exact_manual(table) == pytest.approx(expected, rel=1e-6)


def test_manual_fisher_matches_scipy():
    scipy_stats = pytest.importorskip("scipy.stats")
    for table in ([[7, 13], [2, 18]], [[0, 20], [3, 17]], [[12, 8], [12, 8]]):
        expected = scipy_stats.fisher_exact(table, alternative="two-sided")[1]
        assert analyze.fisher_exact_manual(table) == pytest.approx(expected, rel=1e-9)


def test_fisher_only_at_main_alpha_per_cpus():
    rows = [row("edf", 1, r, 40) for r in range(1, 4)]
    rows += [row("edf_donate", 1, r, 30) for r in range(1, 4)]
    rows += [row("edf", 1, 1, 70, deadline=73, alpha="3.0"),
             row("edf_donate", 1, 1, 60, deadline=73, alpha="3.0")]
    result = analyze.analyze(rows, 1.5)
    assert [(t["cpus"], t["alpha"], t["table"]) for t in result["fisher"]] == [
        (1, "1.5", [[3, 0], [0, 3]])]


def test_main_on_fixture_writes_outputs(tmp_path):
    template = tmp_path / "results_filled.md"
    analyze.main(["--input", str(FIXTURE), "--outdir", str(tmp_path),
                  "--fill-template", str(template)])
    with (tmp_path / "summary.csv").open(newline="") as handle:
        summary = list(csv.DictReader(handle))
    assert tuple(summary[0]) == analyze.SUMMARY_FIELDS
    assert len(summary) == 3 * 2 + 3 * 5  # main cells + sweep cells
    text = (tmp_path / "summary.md").read_text()
    assert "Rows whose miss column disagrees with finish > deadline: 1" in text
    assert "more than one ok row" in text
    assert "miss_kernel" not in text
    filled = template.read_text()
    assert filled.rstrip().endswith("## Anomalies")
    explanation = filled.split("## Explanation", 1)[1].split("## Anomalies", 1)[0]
    assert explanation.strip() == ""


def test_fill_template_without_path_uses_docs_default(monkeypatch, tmp_path):
    # Only the argparse default is checked; the docs file is not written.
    written = []
    monkeypatch.setattr(analyze, "fill_template",
                        lambda result, path, config: written.append(path))
    analyze.main(["--input", str(FIXTURE), "--outdir", str(tmp_path),
                  "--fill-template"])
    assert written == [str(analyze.ROOT / "docs" / "results_template.md")]


def test_fill_template_with_null_w_ticks(tmp_path):
    # The real config has W_ticks null; the parameter cell stays blank.
    out = tmp_path / "t.md"
    analyze.fill_template(analyze.analyze(analyze.read_rows(FIXTURE), 1.5), out,
                          {"W_ticks": None, "harness_workload": {"bytes": 2048}})
    assert "| None | 1.5 |  |" in out.read_text()
