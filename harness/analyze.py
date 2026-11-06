#!/usr/bin/env python3
"""Summarise harness results: miss rates, bootstrap CIs, Fisher exact test.

Rules (nothing else is dropped, smoothed or altered):
  * only rows with status == "ok" are analysed; the others (timeout, panic,
    no_result, bad_result, error, ...) are counted per (policy, cpus, alpha)
    cell and reported with their statuses;
  * miss is recomputed as finish > deadline (the PLAN rule, which wfgen also
    applies); ok rows whose miss column disagrees are reported, and the
    recomputed value is what the statistics use;
  * duplicate (policy, cpus, alpha, run) keys are reported and all ok rows
    are kept;
  * an ok row without integer finish/deadline cannot be analysed; it is
    reported as unparseable rather than skipped silently.
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.config import alpha_label, deadline_for_alpha

POLICIES = ("rr", "edf", "edf_donate")
OK = "ok"
DEFAULT_TEMPLATE = ROOT / "docs" / "results_template.md"
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 20261104
CI_LEVEL = 0.95
SUMMARY_FIELDS = (
    "policy", "cpus", "alpha", "deadline", "n", "misses", "miss_rate",
    "ci_low", "ci_high", "mean_finish", "median_finish", "dropped",
    "dropped_statuses",
)


def read_rows(path):
    """Read a results CSV, skipping '#' comment lines (fixtures).

    Row numbers in reports count data rows: 1 is the first row after the header.
    """
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        lines = [line for line in csv_file if not line.startswith("#")]
    return list(csv.DictReader(lines))


def _int_or_none(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def cell_key(row):
    return (row["policy"], int(row["cpus"]), alpha_label(row["alpha"]))


def cell_sort_key(key):
    policy, cpus, alpha = key
    order = POLICIES.index(policy) if policy in POLICIES else len(POLICIES)
    return (float(alpha), cpus, order, policy)


def percentile(sorted_values, q):
    """Linear-interpolation percentile (numpy's default method)."""
    if not sorted_values:
        raise ValueError("empty sample")
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def bootstrap_ci(outcomes, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
                 level=CI_LEVEL):
    """Percentile bootstrap CI for the mean of 0/1 outcomes.

    A fresh generator per cell makes each cell's CI independent of which
    other cells are present and of their order. With 0 or n misses every
    resample is identical, so the interval collapses to a point.
    """
    if not outcomes:
        return None, None
    rng = random.Random(seed)
    n = len(outcomes)
    means = sorted(sum(rng.choices(outcomes, k=n)) / n for _ in range(resamples))
    tail = (1.0 - level) / 2.0
    return percentile(means, tail), percentile(means, 1.0 - tail)


def _table_probability(a, row1, row2, col1):
    """Hypergeometric probability of a 2x2 table with top-left cell a."""
    total = row1 + row2
    return math.comb(row1, a) * math.comb(row2, col1 - a) / math.comb(total, col1)


def fisher_exact_manual(table):
    """Two-sided Fisher exact p-value for [[a, b], [c, d]].

    Sums the probabilities of every table with the same margins whose
    probability is <= the observed one (the definition R and scipy use);
    the relative tolerance absorbs float rounding between equal tables.
    """
    (a, b), (c, d) = table
    row1, row2, col1 = a + b, c + d, a + c
    if row1 + row2 == 0:
        return 1.0
    observed = _table_probability(a, row1, row2, col1)
    low, high = max(0, col1 - row2), min(row1, col1)
    p_value = 0.0
    for x in range(low, high + 1):
        probability = _table_probability(x, row1, row2, col1)
        if probability <= observed * (1 + 1e-7):
            p_value += probability
    return min(1.0, p_value)


def fisher_exact(table):
    """Return (p_value, method) using scipy if importable."""
    try:
        from scipy.stats import fisher_exact as scipy_fisher
    except ImportError:
        return fisher_exact_manual(table), "manual (hypergeometric, two-sided)"
    return float(scipy_fisher(table, alternative="two-sided")[1]), "scipy.stats.fisher_exact"


def analyze(rows, main_alpha):
    """Apply the rules above and return a dict of results and reports."""
    dropped = defaultdict(Counter)
    ok_rows = defaultdict(list)
    mismatches = []
    unparseable = []
    key_rows = defaultdict(list)

    for index, row in enumerate(rows, start=1):
        key = cell_key(row)
        key_rows[key + (int(row["run"]),)].append((index, row["status"]))
        if row["status"] != OK:
            dropped[key][row["status"] or "(empty)"] += 1
            continue
        finish = _int_or_none(row.get("finish"))
        deadline = _int_or_none(row.get("deadline"))
        if finish is None or deadline is None:
            unparseable.append((index, row))
            continue
        host_miss = 1 if finish > deadline else 0
        if _int_or_none(row.get("miss")) != host_miss:
            mismatches.append({
                "row": index, "policy": key[0], "cpus": key[1], "alpha": key[2],
                "run": row["run"], "finish": finish, "deadline": deadline,
                "miss_column": row.get("miss"), "host_miss": host_miss,
            })
        ok_rows[key].append({
            "finish": finish, "deadline": deadline, "miss": host_miss, "row": row,
        })

    duplicates = []
    for key, entries in sorted(key_rows.items(),
                               key=lambda item: cell_sort_key(item[0][:3]) + (item[0][3],)):
        if len(entries) > 1:
            oks = sum(1 for _, status in entries if status == OK)
            duplicates.append({"key": key, "entries": entries,
                               "multiple_ok": oks > 1})

    summary = []
    for key in sorted(set(ok_rows) | set(dropped), key=cell_sort_key):
        entries = ok_rows.get(key, [])
        outcomes = [entry["miss"] for entry in entries]
        finishes = [entry["finish"] for entry in entries]
        deadlines = sorted({entry["deadline"] for entry in entries})
        ci_low, ci_high = bootstrap_ci(outcomes)
        n = len(outcomes)
        # .get, not [], so cells without drops do not gain empty entries.
        cell_dropped = dropped.get(key, Counter())
        summary.append({
            "policy": key[0], "cpus": key[1], "alpha": key[2],
            "deadline": ";".join(str(value) for value in deadlines),
            "n": n,
            "misses": sum(outcomes),
            "miss_rate": sum(outcomes) / n if n else None,
            "ci_low": ci_low, "ci_high": ci_high,
            "mean_finish": statistics.mean(finishes) if finishes else None,
            "median_finish": statistics.median(finishes) if finishes else None,
            "dropped": sum(cell_dropped.values()),
            "dropped_statuses": ";".join(
                "{}:{}".format(status, count)
                for status, count in sorted(cell_dropped.items())),
        })

    fisher = []
    main_label = alpha_label(main_alpha)
    for cpus in sorted({key[1] for key in ok_rows if key[2] == main_label}):
        edf = ok_rows.get(("edf", cpus, main_label), [])
        donate = ok_rows.get(("edf_donate", cpus, main_label), [])
        if not edf or not donate:
            continue
        edf_miss = sum(entry["miss"] for entry in edf)
        donate_miss = sum(entry["miss"] for entry in donate)
        table = [[edf_miss, len(edf) - edf_miss],
                 [donate_miss, len(donate) - donate_miss]]
        p_value, method = fisher_exact(table)
        fisher.append({"cpus": cpus, "alpha": main_label, "table": table,
                       "p_value": p_value, "method": method})

    commits = sorted({entry["row"].get("commit_hash", "")
                      for entries in ok_rows.values() for entry in entries})
    return {
        "summary": summary, "dropped": dropped, "mismatches": mismatches,
        "unparseable": unparseable, "duplicates": duplicates,
        "fisher": fisher, "main_alpha": main_label, "commits": commits,
        "ok": ok_rows,
    }


def _fmt(value, digits=3):
    if value is None:
        return ""
    if isinstance(value, float):
        return "{:.{}f}".format(value, digits)
    return str(value)


def write_summary_csv(result, path):
    with Path(path).open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in result["summary"]:
            writer.writerow({field: _fmt(row[field], 4) for field in SUMMARY_FIELDS})


def _summary_table(rows):
    lines = [
        "| policy | cpus | alpha | deadline | n | misses | miss rate | 95% CI | "
        "mean finish | median finish | dropped |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        ci = ("[{}, {}]".format(_fmt(row["ci_low"], 2), _fmt(row["ci_high"], 2))
              if row["n"] else "")
        dropped = str(row["dropped"])
        if row["dropped"]:
            dropped += " ({})".format(row["dropped_statuses"])
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            row["policy"], row["cpus"], row["alpha"], row["deadline"], row["n"],
            row["misses"], _fmt(row["miss_rate"], 2), ci,
            _fmt(row["mean_finish"], 1), _fmt(row["median_finish"], 1), dropped))
    return lines


def _fisher_lines(result):
    lines = [
        "| cpus | alpha | edf miss/met | edf_donate miss/met | p (two-sided) | method |",
        "|---|---|---|---|---|---|",
    ]
    for test in result["fisher"]:
        (a, b), (c, d) = test["table"]
        lines.append("| {} | {} | {}/{} | {}/{} | {:.4g} | {} |".format(
            test["cpus"], test["alpha"], a, b, c, d, test["p_value"], test["method"]))
    if not result["fisher"]:
        lines.append("| | | | | | no cell has both edf and edf_donate at the main alpha |")
    sizes = [sum(row) for test in result["fisher"] for row in test["table"]]
    lines.append("")
    lines.append("Note: n is small (largest n per cell here: {}), so the test has "
                 "little power; a large p-value does not show the policies are "
                 "equivalent.".format(max(sizes) if sizes else 0))
    return lines


def _quality_lines(result):
    lines = []
    total_dropped = sum(sum(c.values()) for c in result["dropped"].values())
    lines.append("- Non-ok rows dropped: {}".format(total_dropped))
    for key in sorted(result["dropped"], key=cell_sort_key):
        statuses = ", ".join("{} x{}".format(s, n)
                             for s, n in sorted(result["dropped"][key].items()))
        lines.append("  - {} cpus={} alpha={}: {}".format(key[0], key[1], key[2], statuses))
    lines.append("- Rows whose miss column disagrees with finish > deadline: {}".format(
        len(result["mismatches"])))
    for item in result["mismatches"]:
        lines.append("  - data row {row}: {policy} cpus={cpus} alpha={alpha} run={run} "
                     "finish={finish} deadline={deadline} miss column={miss_column} "
                     "host rule={host_miss}".format(**item))
    lines.append("- ok rows without integer finish/deadline (not analysed): {}".format(
        len(result["unparseable"])))
    for index, row in result["unparseable"]:
        lines.append("  - data row {}: {}".format(index, dict(row)))
    lines.append("- Duplicate (policy, cpus, alpha, run) keys: {}".format(
        len(result["duplicates"])))
    for item in result["duplicates"]:
        policy, cpus, alpha, run = item["key"]
        entries = ", ".join("data row {} {}".format(i, s) for i, s in item["entries"])
        flag = " (more than one ok row; all kept)" if item["multiple_ok"] else ""
        lines.append("  - {} cpus={} alpha={} run={}: {}{}".format(
            policy, cpus, alpha, run, entries, flag))
    return lines


def write_summary_md(result, path, input_path):
    lines = [
        "# Stage 7 summary",
        "",
        "Generated by harness/analyze.py from `{}`.".format(input_path),
        "Miss rule: miss = 1 if finish > deadline (computed by wfgen, rechecked here).",
        "Bootstrap: {} resamples, seed {}, percentile {:.0f}% interval.".format(
            BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, CI_LEVEL * 100),
        "Commit hashes in analysed rows: {}".format(", ".join(result["commits"]) or "none"),
        "",
        "## Per-cell results",
        "",
    ]
    lines += _summary_table(result["summary"])
    lines += ["", "When misses are 0 or n the bootstrap interval collapses to a "
              "point; that reflects the method, not certainty.", "",
              "## Fisher exact test: edf vs edf_donate (alpha {})".format(result["main_alpha"]),
              ""]
    lines += _fisher_lines(result)
    lines += ["", "## Data quality", ""]
    lines += _quality_lines(result)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def fill_template(result, path, config):
    """Write the results document with tables only.

    The default target is docs/results_template.md. Explanation and
    Anomalies stay as empty headings for the team to write by hand. With
    W_ticks still null (not yet recalibrated) the deadline cell is blank.
    """
    main = result["main_alpha"]
    workload = config.get("harness_workload", {})
    lines = [
        "# Stage 7 results",
        "",
        "## Parameters",
        "",
        "| W (ticks) | main alpha | deadline at main alpha | stages | work | bytes | "
        "hogs (CPUS=1 / CPUS=3) | commit hashes |",
        "|---|---|---|---|---|---|---|---|",
        "| {} | {} | {} | {} | {} | {} | {} / {} | {} |".format(
            config.get("W_ticks"), main,
            (deadline_for_alpha(main, config["W_ticks"])
             if config.get("W_ticks") is not None else ""),
            workload.get("stages", ""), workload.get("work", ""),
            workload.get("bytes", ""),
            config.get("hogs_by_cpus", {}).get("1", ""),
            config.get("hogs_by_cpus", {}).get("3", ""),
            ", ".join(result["commits"])),
        "",
        "## Miss rate at the main alpha",
        "",
    ]
    lines += _summary_table([row for row in result["summary"] if row["alpha"] == main])
    lines += ["", "## Miss rate vs alpha (CPUS=1)", ""]
    lines += _summary_table([row for row in result["summary"] if row["cpus"] == 1])
    lines += ["", "## Fisher exact test: edf vs edf_donate", ""]
    lines += _fisher_lines(result)
    lines += ["", "## Data quality", ""]
    lines += _quality_lines(result)
    lines += ["", "## Explanation", "", "", "## Anomalies", "", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=str(ROOT / "results" / "results.csv"))
    parser.add_argument("--outdir", default=str(ROOT / "results"))
    parser.add_argument("--config", default=str(ROOT / "host" / "config.json"))
    parser.add_argument("--main-alpha", type=float, default=None,
                        help="alpha for the Fisher test (default: config alpha)")
    parser.add_argument("--fill-template", metavar="OUT", nargs="?", default=None,
                        const=str(DEFAULT_TEMPLATE),
                        help="also write the tables-only results document to OUT "
                             "(default when given without OUT: {})".format(
                                 DEFAULT_TEMPLATE.relative_to(ROOT)))
    args = parser.parse_args(argv)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    main_alpha = args.main_alpha if args.main_alpha is not None else config["alpha"]
    result = analyze(read_rows(args.input), main_alpha)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_summary_csv(result, outdir / "summary.csv")
    write_summary_md(result, outdir / "summary.md", args.input)
    if args.fill_template:
        Path(args.fill_template).parent.mkdir(parents=True, exist_ok=True)
        fill_template(result, args.fill_template, config)

    print("\n".join(_summary_table(result["summary"])))
    print()
    print("\n".join(_fisher_lines(result)))
    print()
    print("\n".join(_quality_lines(result)))
    print()
    print("Wrote {} and {}".format(outdir / "summary.csv", outdir / "summary.md"))
    if args.fill_template:
        print("Wrote {}".format(args.fill_template))


if __name__ == "__main__":
    main()
