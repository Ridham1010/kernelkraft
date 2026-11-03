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