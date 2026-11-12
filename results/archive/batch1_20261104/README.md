# Archive v1: first Stage 7 batch (superseded)

This folder holds the first Stage 7 measurement batch. It is kept for the
record and is **superseded** by the PLAN-conformant batch that will be written
to `results/results.csv`. Do not cite these numbers as the final results.

| Item | Value |
|---|---|
| Commit | `043a34b5` |
| Workload | `wfgen 4 100 1024 <deadline> <hogs>` (bytes 1024 < 4 x PIPESIZE) |
| W (unloaded ticks) | 24.4 |
| Alphas | 1.0, 1.25, 1.5, 2.0, 2.5, 3.0 (range 1.0-3.0) |
| CSV format | 11 columns (extra `miss_kernel`), status `success` |

Why superseded: in this version wfgen started its clock before forking the
hogs and reported the kernel's cumulative per-boot miss counter as `miss`.
The workload bytes and alpha set did not follow docs/PLAN.md (Stages 6 and 7).

Contents:

- `results.csv`, `summary.csv`, `summary.md`: main batch and sweep, plus analysis
- `smoke.csv`: smoke test
- `order_check.csv`: ordering check
- `plots/`: `misses_bar`, `miss_vs_alpha`, `finish_box` (PNG and `.sources.txt`)
  and the Gantt charts `gantt-T57-edf.png`, `gantt-T58-edf_donate.png`,
  `gantt-T58-miss.png`

Raw logs were not moved. They are still in `logs/run_20261104/`,
`logs/smoke_20261104/` and `logs/order_check_20261104/`.

The paths inside the `.sources.txt` sidecars, and the `rawlog_path` column of
the CSVs, refer to the **pre-archive** locations (for example
`results/results.csv` and `host/plots/`). Read them with this folder in mind.
