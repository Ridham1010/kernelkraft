# Parameters

The authoritative shared kernel/user values are in
[`xv6-public/sched_params.h`](../xv6-public/sched_params.h); host values are
in [`host/config.json`](../host/config.json).

| Parameter | Value | Notes |
|---|---:|---|
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
| `hogs` (CPUS=3) | 5 | Host harness selection; at least cpus + 1 |

## Trace Ring Parameters

| Parameter | Value | Notes |
|---|---:|---|
| `TRACE_SIZE` | 256 | Per-CPU trace ring capacity (entries) |
| `NCPU` | 1 or 3 | Number of CPUs (configured at boot) |

## Stage 7: Final Parameters

| Parameter | Value | Notes |
|---|---:|---|
| `W` (ticks per calibrated workload) | 24.4 | Mean of runs 2-6 of `logs/stage7-calibration-postfix/`: 23, 27, 27, 22, 23 ticks; SD 2.41. Fixed kernel (305a13f), CPUS=1, zero hogs, machine flag. Run 1 was aborted by the operator before input; its log is kept. Pre-fix W was 25.4 (`logs/stage7-calibration/`). The Stage 6 value 13.6 was for 2 stages. |
| Deadline rule | round(α × W) | Half-up rounding, so 1.25 × 24.4 = 30.5 gives 31 |
| `α` (main) | 1.5 | Deadline 37; chosen from a pilot (`logs/stage7-pilot-postfix/`) and disclosed in `docs/predictions.md` |
| `α` (sweep) | 1.0, 1.25, 1.5, 2.0, 2.5, 3.0 | CPUS=1 only |
| `stages` | 4 | `wfgen 4 100 1024 <deadline> <hogs>` |
| `work` | 100 | CPU work units per stage |
| `bytes` | 1024 | Pipeline data size |
| `hogs` (CPUS=1) | 3 | `host/config.json` `hogs_by_cpus` |
| `hogs` (CPUS=3) | 5 | `host/config.json` `hogs_by_cpus` |
| Runs per cell (main batch) | 20 | 3 policies × CPUS 1, 3 at α = 1.5 |
| Runs per cell (sweep) | 10 | CPUS=1, all six α values; α = 1.5 runs 1-10 are reused from the main batch |
| QEMU machine flag | `-machine pc-i440fx-yakkety` | QEMU 10.1.0; carried by `host/config.json` `qemu_extra` and passed by the harness. Without it xv6 starts only cpu0 (see L-24). |

### Stage 7: Deadline per α

| `α` | Deadline (ticks) |
|---|---:|
| 1.0 | 24 |
| 1.25 | 31 |
| 1.5 | 37 |
| 2.0 | 49 |
| 2.5 | 61 |
| 3.0 | 73 |

### Stage 7: Commits

| Commit | Content |
|---|---|
| 305a13f | Kernel fix: `NO_DEADLINE` ordering in `dl_before` |
| 2dcf16c | Predictions, committed before the batch |
| 043a34b | Code: harness sweep, analysis, plots, adaptive planner. Every batch row carries `commit_hash` 043a34b5. |
| a314e13 | Data: full batch, logs, plots, audit |
