# System calls

| Number | Name | Arguments | Result | Notes |
|---:|---|---|---|---|
| 22 | `hello` | `int hello(void)` | `0` | Implemented by `sysproc.c`; prints `hello from kernel`; syscall setup is documented in the Stage 1 plan. |
| 23 | `add` | `int add(int a, int b)` | `a + b` | Implemented by `sysproc.c`; simple addition test syscall. |
| 24 | `setsched` | `int setsched(int policy)` | `0` on success, `-1` on error | Sets scheduling policy: 0=RR (original), 1=EDF, 2=EDF with donation (stub). Updates global `sched_policy`. Returns `-1` if policy not in 0..2. |
| 25 | `setworkflow` | `int setworkflow(int wid, int deadline)` | `0` on success, `-1` on error | Assigns process to workflow `wid` (1..NWF-1) with relative `deadline` (ticks). First caller sets absolute deadline = `now_ticks() + deadline`. Subsequent callers must match. Rejects if `wid<=0`, `wid>=NWF`, `deadline<=0`, or process already has a workflow. Returns `-1` on error. |
| 26 | `schedinfo` | `int schedinfo(struct sched_stats *stats)` | `0` on success, `-1` on error | Fills `stats` with current scheduler statistics: policy, ncpu, ticks, misses, donations, cycles, rejected. Returns `-1` if user pointer invalid. |

