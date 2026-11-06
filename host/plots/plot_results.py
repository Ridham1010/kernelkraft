#!/usr/bin/env python3
"""Plot Stage 7 results from analyze.py's summary.csv and the harness CSV.

Writes misses_bar.png, miss_vs_alpha.png and finish_box.png, each with a
<name>.sources.txt sidecar (input CSVs, commit hashes, raw-log directories
of the rows behind the graph) that tools/index_evidence.py reads.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.config import alpha_label
from harness.analyze import OK, POLICIES, read_rows

POLICY_COLORS = {"rr": "tab:gray", "edf": "tab:orange", "edf_donate": "tab:blue"}


def read_summary(path):
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    for row in rows:
        row["cpus"] = int(row["cpus"])
        row["alpha"] = alpha_label(row["alpha"])
        row["n"] = int(row["n"])
        for field in ("miss_rate", "ci_low", "ci_high"):
            row[field] = float(row[field]) if row[field] != "" else None
    return rows


def ok_rows(results, keep):
    """Status-ok rows of the harness CSV for which keep(policy, cpus, alpha)."""
    return [row for row in results
            if row["status"] == OK
            and keep(row["policy"], int(row["cpus"]), alpha_label(row["alpha"]))]


def write_sources(png_path, inputs, rows):
    """Record where a graph came from, one 'key: value' per line."""
    lines = ["graph: {}".format(png_path.name)]
    lines += ["input_csv: {}".format(path) for path in inputs]
    lines.append("rows_used: {}".format(len(rows)))
    for commit in sorted({row.get("commit_hash", "") for row in rows}):
        lines.append("commit_hash: {}".format(commit))
    for directory in sorted({str(Path(row["rawlog_path"]).parent) for row in rows
                             if row.get("rawlog_path")}):
        lines.append("rawlog_dir: {}".format(directory))
    sidecar = png_path.with_suffix(".sources.txt")
    sidecar.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sidecar


def _yerr(rows):
    """Asymmetric error bars from the bootstrap CI columns."""
    lower = [row["miss_rate"] - row["ci_low"] for row in rows]
    upper = [row["ci_high"] - row["miss_rate"] for row in rows]
    return [lower, upper]


def plot_misses_bar(summary, results, main_alpha, inputs, outdir):
    cpus_values = sorted({row["cpus"] for row in summary if row["alpha"] == main_alpha})
    fig, ax = plt.subplots(figsize=(7, 4))
    width = 0.8 / len(POLICIES)
    labelled = set()
    for index, policy in enumerate(POLICIES):
        for position, cpus in enumerate(cpus_values):
            matches = [row for row in summary if row["policy"] == policy
                       and row["cpus"] == cpus and row["alpha"] == main_alpha
                       and row["n"] > 0]
            if not matches:
                continue
            row = matches[0]
            x = position + (index - (len(POLICIES) - 1) / 2) * width
            ax.bar(x, row["miss_rate"], width, yerr=_yerr([row]), capsize=4,
                   color=POLICY_COLORS[policy],
                   label="" if policy in labelled else policy)
            labelled.add(policy)
            ax.text(x, min(1.02, row["ci_high"] + 0.03), "n={}".format(row["n"]),
                    ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(len(cpus_values)))
    ax.set_xticklabels(["CPUS={}".format(c) for c in cpus_values])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("miss rate (finish > deadline)")
    ax.set_title("Deadline misses at alpha={} (95% bootstrap CI)".format(main_alpha))
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    png = outdir / "misses_bar.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    rows = ok_rows(results, lambda p, c, a: p in POLICIES and a == main_alpha
                   and c in cpus_values)
    return png, write_sources(png, inputs, rows)


def plot_miss_vs_alpha(summary, results, inputs, outdir, cpus=1):
    fig, ax = plt.subplots(figsize=(7, 4))
    for policy in POLICIES:
        rows = sorted((row for row in summary if row["policy"] == policy
                       and row["cpus"] == cpus and row["n"] > 0),
                      key=lambda row: float(row["alpha"]))
        if not rows:
            continue
        ax.errorbar([float(row["alpha"]) for row in rows],
                    [row["miss_rate"] for row in rows], yerr=_yerr(rows),
                    marker="o", capsize=4, color=POLICY_COLORS[policy], label=policy)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("alpha (deadline = round(alpha * W))")
    ax.set_ylabel("miss rate (finish > deadline)")
    ax.set_title("Miss rate vs alpha, CPUS={} (95% bootstrap CI)".format(cpus))
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    png = outdir / "miss_vs_alpha.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    rows = ok_rows(results, lambda p, c, a: p in POLICIES and c == cpus)
    return png, write_sources(png, inputs, rows)


def plot_finish_box(results, main_alpha, inputs, outdir):
    rows = ok_rows(results, lambda p, c, a: p in POLICIES and a == main_alpha)
    cpus_values = sorted({int(row["cpus"]) for row in rows})
    fig, axes = plt.subplots(1, max(1, len(cpus_values)),
                             figsize=(5 * max(1, len(cpus_values)), 4), squeeze=False)
    for ax, cpus in zip(axes[0], cpus_values):
        data, labels = [], []
        for policy in POLICIES:
            finishes = [int(row["finish"]) for row in rows
                        if row["policy"] == policy and int(row["cpus"]) == cpus]
            if finishes:
                data.append(finishes)
                labels.append("{}\n(n={})".format(policy, len(finishes)))
        if data:
            ax.boxplot(data)
            ax.set_xticks(range(1, len(labels) + 1))
            ax.set_xticklabels(labels)
        # Every row at one alpha shares a deadline; draw each distinct value
        # anyway so a mixed CSV is visible rather than hidden.
        deadlines = sorted({int(row["deadline"]) for row in rows
                            if int(row["cpus"]) == cpus})
        for deadline in deadlines:
            ax.axhline(deadline, color="red", linestyle="--", linewidth=1,
                       label="deadline = {} ticks".format(deadline))
        ax.set_title("CPUS={}".format(cpus))
        ax.set_ylabel("finish (ticks)")
        ax.legend(fontsize=8)
    fig.suptitle("Workflow finish time at alpha={}".format(main_alpha))
    fig.tight_layout()
    png = outdir / "finish_box.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    return png, write_sources(png, inputs, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_csv")
    parser.add_argument("results_csv")
    parser.add_argument("--outdir", default=str(ROOT / "results"))
    parser.add_argument("--config", default=str(ROOT / "host" / "config.json"))
    parser.add_argument("--main-alpha", type=float, default=None,
                        help="alpha for misses_bar and finish_box (default: config alpha)")
    args = parser.parse_args(argv)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    main_alpha = alpha_label(args.main_alpha if args.main_alpha is not None
                             else config["alpha"])
    summary = read_summary(args.summary_csv)
    results = read_rows(args.results_csv)
    inputs = [args.results_csv, args.summary_csv]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for png, sidecar in (
            plot_misses_bar(summary, results, main_alpha, inputs, outdir),
            plot_miss_vs_alpha(summary, results, inputs, outdir),
            plot_finish_box(results, main_alpha, inputs, outdir)):
        print("Wrote {} and {}".format(png, sidecar))


if __name__ == "__main__":
    main()
