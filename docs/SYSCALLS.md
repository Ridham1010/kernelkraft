# System calls

| Number | Name | Arguments | Result | Notes |
|---:|---|---|---|---|
| 22 | `hello` | `int hello(void)` | `0` | Implemented by `sysproc.c`; prints `hello from kernel`; syscall setup is documented in the Stage 1 plan. |
| 23 | `add` | `int add(int a, int b)` | `a + b` | Implemented by `sysproc.c`; simple addition test syscall. |
| 24 | `setsched` | `int setsched(int policy)` | `0` on success, `-1` on error | Sets scheduling policy: 0=RR (original), 1=EDF, 2=EDF with donation. The kernel boots in policy 2 (`DEFAULT_POLICY`). Leaving policy 2 withdraws all donations; entering it rebuilds them. Returns `-1` if policy not in 0..2. |
| 25 | `setworkflow` | `int setworkflow(int wid, int deadline)` | `0` on success, `-1` on error | Assigns the process to workflow `wid` (any positive integer) with relative `deadline` (ticks). The first caller creates the workflow with absolute deadline = `now_ticks() + deadline`. Later callers join it and share that deadline; their `deadline` argument is not used. Rejects if `wid<=0`, `deadline<=0`, the process already has a workflow, admission refuses it (slack below `MIN_SLACK` for a new workflow, or `MAX_URGENT` reached), or all `NWF` slots are in use. A refused call leaves no workflow behind. |
| 26 | `schedinfo` | `int schedinfo(struct sched_stats *stats)` | `0` on success, `-1` on error | Fills `stats` with current scheduler statistics: policy, ncpu, ticks, misses, donations, cycles, rejected. Returns `-1` if user pointer invalid. |
| 27 | `tracectl` | `int tracectl(int command)` | `0` on success, `-1` on error | Command 0: disable trace, 1: enable trace, 2: clear rings, 3: enable donation debug prints, 4: disable donation debug prints. |
| 28 | `procinfo` | `int procinfo(int pid, struct procstat *dst)` | `0` on success, `-1` if pid is not found or the pointer is invalid | Copies state, own deadline, donated deadline, and whether the process is waiting on a pipe. |
| 29 | `schedtrace` | `int schedtrace(struct trace_ent *dst, int max)` | Number of entries copied, `-1` on error | Copies at most `max` entries total from the per-CPU rings, oldest-first within each CPU. The complete user buffer is validated before copying. |
