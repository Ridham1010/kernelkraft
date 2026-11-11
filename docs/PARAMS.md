# Parameters

The authoritative shared kernel/user values are in
[`xv6-public/sched_params.h`](../xv6-public/sched_params.h); host values are
in [`host/config.json`](../host/config.json).

| Parameter | Value | Notes |
|---|---:|---|
| `DEFAULT_POLICY` | 2 | Policy at boot (0=rr, 1=edf, 2=edf_donate) |
| `MIN_SLACK` | 20 | Admission: minimum relative deadline (ticks) for a new workflow |
| `MAX_URGENT` | 64 | Admission: cap on live processes with their own deadline; equal to `NPROC`, so it does not refuse a process the table could hold |
| `NWF` | 16 | Workflows alive at once; any positive `wid` is valid |
| `DONATION_EVENT_MAX` | 32 | Donation events buffered per pipe wait for the print mode |
| `MIN_STAGES` | 2 | Host validator lower bound for pipeline length |
| `MAX_STAGES` | 6 | Host validator upper bound for pipeline length |
| `MIN_WORK` | 1 | Host validator lower bound for stage work |
| `MAX_WORK` | 1000000 | Host validator upper bound for stage work |
| `MIN_BYTES` | 1 | Host validator lower bound for pipeline bytes |
| `MAX_BYTES` | 1000000 | Host validator upper bound for pipeline bytes |

## Stage 6: Workload Calibration Parameters

| Parameter | Value | Notes |
|---|---:|---|
| `W` (ticks per calibrated workload) | 13.6 | Mean of five CPUS=1, zero-hog runs: 14, 13, 13, 14, 14; SD 0.55 |
| `α` (deadline tightness factor) | 1.0, 2.0, 5.0 | Configured host values; the harness default is `alpha=1.0` |
| `bytes` | 1024, 4096 | Pipeline data size per stage |
| `work` | 100, 500, 1000 | CPU work units per stage |
| `hogs` (CPUS=1) | 3 | Host harness selection; at least cpus + 1 |
| `hogs` (CPUS=3) | 8 | Host harness selection; at least cpus + 1. Raised from 5 on 2026-11-11 because 5 hogs did not load three CPUs enough to separate the policies |

## Trace Ring Parameters

| Parameter | Value | Notes |
|---|---:|---|
| `TRACE_SIZE` | 256 | Per-CPU trace ring capacity (entries) |
| `NCPU` | 1 or 3 | Number of CPUs (configured at boot) |

## Stage 7: Final Parameters

These values describe the PLAN-conformant second batch (`results/results.csv`).

| Parameter | Value | Notes |
|---|---:|---|
| `W` (ticks per calibrated workload) | 48.2 | Mean of runs 1-5 of `logs/stage7rev-calibration/`: 46, 51, 50, 45, 49 ticks; sample SD 2.59. `wfgen 4 100 2048 300 0`, edf, CPUS=1, zero hogs, machine flag. Run 2 contains a mistyped command (exec fail) before the real one; the measurement is the later `RESULT` line. Stored as `W_ticks` in `host/config.json`. |
| Deadline rule | round(α × W) | Half-up rounding |
| Deadline window | W < D < (h+1)W | 48.2 to 192.8 ticks for h = 3; every deadline below lies inside it |
| `α` (main) | 1.5 | Deadline 72 |
| `α` (sweep) | 1.2, 1.5, 2.0, 3.0 | CPUS=1 only; `host/config.json` `alpha_values` |
| `stages` | 4 | `wfgen 4 100 2048 <deadline> <hogs>` |
| `work` | 100 | CPU work units per stage |
| `bytes` | 2048 | Pipeline data size; PLAN requires bytes ≥ 4 × PIPESIZE (512) |
| `MIN_PIPELINE_BYTES` | 2048 | `host/config.json`; the harness refuses to start if `harness_workload.bytes` is below it |
| `hogs` (CPUS=1) | 3 | `host/config.json` `hogs_by_cpus` |
| `hogs` (CPUS=3) | 8 | `host/config.json` `hogs_by_cpus` |
| Runs per cell (main batch) | 20 | 3 policies × CPUS 1, 3 at α = 1.5 |
| Runs per cell (sweep) | 10 | CPUS=1, all four α values; α = 1.5 runs 1-10 are reused from the main batch. 10 runs per sweep cell instead of 20, as PLAN allows when time is short. |
| QEMU machine flag | `-machine pc-i440fx-yakkety` | QEMU 10.1.0; carried by `host/config.json` `qemu_extra` and passed by the harness. Without it xv6 starts only cpu0 (see L-24). |

### Stage 7: Deadline per α

| `α` | Deadline (ticks) |
|---|---:|
| 1.2 | 58 |
| 1.5 | 72 |
| 2.0 | 96 |
| 3.0 | 145 |

### Stage 7: Commits

| Commit | Content |
|---|---|
| 305a13f | Kernel fix: `NO_DEADLINE` ordering in `dl_before` (still in force) |
| 066060f | Code aligned with PLAN.md: wfgen clock and miss rule, config, `harness/` layout, 10-column CSV, status `ok` |
| 7fba9fa | W calibration 48.2 ticks (`logs/stage7rev-calibration/`); `W_ticks` set in `host/config.json` |
| cb7a589 | Predictions Revision 2 and pilot (`results/pilot_rev.csv`, `logs/stage7rev-pilot/`), committed before the batch. Every second-batch row carries `commit_hash` cb7a589b; pilot rows carry 7fba9fae. |
| d5f9314 | Data: second batch (210 rows), summary, plots, T-57/T-58 traces |
| f3ab258 | T-59 adaptive agent rerun |

### Archived first batch

The first Stage 7 batch did not match PLAN.md and is archived in `results/archive_v1/` (see its README).

| Parameter | Value |
|---|---|
| `W` | 24.4 ticks (runs 2-6 of `logs/stage7-calibration-postfix/`: 23, 27, 27, 22, 23; SD 2.41) |
| Workload | `wfgen 4 100 1024 <deadline> <hogs>` |
| `α` (main) | 1.5 (deadline 37) |
| `α` (sweep) | 1.0, 1.25, 1.5, 2.0, 2.5, 3.0 (deadlines 24, 31, 37, 49, 61, 73) |
| Commits | 2dcf16c (predictions), 043a34b (code; every row carries `commit_hash` 043a34b5), a314e13 (data) |
