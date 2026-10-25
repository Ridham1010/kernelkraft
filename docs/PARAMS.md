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
