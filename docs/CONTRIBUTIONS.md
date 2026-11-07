# Contributions

## Per-person highlights

| Contributor | Files/functions | Tests or evidence |
|---|---|---|
| Ridham1010 | `xv6-public/proc.c` scheduler, donation, trace ring; `host/harness/run_all.py` | T-34--T-60; Stage 7 result sweep |
| Pranav Nair | `host/bridge/`, validator/planner integration, `host/tests/` | T-14--T-26; validator and bridge tests |
| Atharv | `xv6-public/wfgen.c`, user workload programs, Stage 4 admission paths | T-25--T-32; T-46--T-53 |
| Ridham Shah | documentation, evidence index, packaging scripts and final audit | T-00b, T-60, Stage 8 checker |

`git shortlog -sn` at the final audit:

```text
17	Ridham1010
14	Pranav Nair
10	Atharv
1	Ridham Shah
```

| Contributor | Work |
|---|---|
| Team | Stage 1 hello syscall, tick test, filesystem capacity, and QEMU bridge |
| Team | Stage 2 runtime policy switch, baseline EDF scheduler, workflow management, new syscalls (setsched, setworkflow, schedinfo), user programs (schedctl, schedstat, edftest) |
| Team | Stage 3 bridge framing, validated tool registry, planners, audit loop, and guest sentinel tools |
| Team | Stage 4 admission control, firm deadlines, workflow generator, injection demo, and documentation |
| Team | Stage 5 pipe donation, cycle-safe traversal, withdrawal recomputation, procinfo/tracectl, tests, and documentation |
| Team | Stage 6 trace ring, rdtsc timestamps, schedtrace/tracectl syscalls, wfgen/schedtrace/calib user programs, harness, Gantt plotter, and documentation |
| Team | Stage 7 measurement harness sweep, analysis (bootstrap, Fisher), result plots, adaptive planner, dl_before fix, PLAN alignment rerun, and documentation |
