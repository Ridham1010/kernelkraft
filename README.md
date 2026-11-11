# kernelkraft

CSL3030 OS Lab project: an earliest-deadline-first scheduler for xv6 with
priority donation through pipes, plus a host-side agent and measurement
harness.

## Layout

| Path | Contents |
|---|---|
| `xv6-public/` | Kernel and user programs. Scheduler and donation: `proc.c`, `pipe.c`. Parameters: `sched_params.h` |
| `host/` | Host-side agent, validator, bridge and plots |
| `harness/` | Batch runner (`run_all.py`) and analysis (`analyze.py`) |
| `docs/` | Design, syscalls, parameters, limitations, test table, journal |
| `results/`, `logs/` | Measurement output and raw QEMU logs |
| `tools/` | Submission check and packaging scripts |

## Build and run

```sh
cd xv6-public
make
make qemu-nox CPUS=1
make qemu-nox CPUS=3 QEMUEXTRA="-machine pc-i440fx-yakkety"
```

The kernel boots in EDF with donation. Inside xv6:

```
schedctl rr | edf | edf_donate     select the policy
schedstat                          policy and counters
tracectl 3                         print each donation
wfgen <stages> <work> <bytes> <deadline> <hogs>
donate5  cycletest  killtest  donatetest  wftest  test_negative
```

## Measurements

```sh
python3 harness/run_all.py --alphas 1.5 --cpus 1,3 --runs 20
python3 harness/analyze.py
```

See `docs/DESIGN.md` for the design and `docs/LIMITATIONS.md` for known gaps.
