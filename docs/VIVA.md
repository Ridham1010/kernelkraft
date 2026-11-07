# Viva notes

| Question | Answer |
|---|---|
| Why two deadline fields (`deadline` and `donated`)? | The `deadline` field stores the process's own absolute deadline (from its workflow). The `donated` field allows priority donation: when a low-priority process holds a resource needed by a high-priority process, the high-priority process can "donate" its earlier deadline to the low-priority process, which then runs with `effective(p) = min(deadline, donated)`. This prevents priority inversion. |
| Why tie-break on `last_run` with `<` instead of `<=`? | Using `<` (strict less-than) ensures that when two processes have equal effective deadlines and equal `last_run` (which shouldn't happen with a monotonically increasing counter, but is theoretically possible on wrap), the comparison is false and the first process encountered keeps priority. Using `<=` would cause the later process to win, leading to index starvation where lower-indexed processes in the `ptable` array could never get scheduled when they tie with higher-indexed ones. |
| Why wrap-safe compare with `(int)(a-b) < 0`? | The `ticks` counter is a 32-bit unsigned integer that wraps from `0xFFFFFFFF` to `0`. A plain `a < b` comparison fails near wrap: e.g., if current `ticks = 0xFFFFFF00`, a deadline at `0xFFFFFF10` (16 ticks away) would appear *greater than* a deadline at `0x00000020` (32 ticks away but numerically smaller). Signed subtraction correctly computes the modular distance: `(int)(0xFFFFFF10 - 0x00000020) = -16 < 0`, correctly identifying the earlier deadline. |
| Is the wrap-safe compare still `(int)(a-b) < 0`? | Superseded by 305a13f: dl_before first treats NO_DEADLINE as latest, then applies (int)(a - b) < 0. |
| Why is `now_ticks()` an unlocked read? | The scheduler holds `ptable.lock` when calling `now_ticks()`. Acquiring `tickslock` while holding `ptable.lock` would violate the lock order (`tickslock -> ptable.lock`). Since `ticks` is 32-bit aligned on x86, a volatile read is atomic and safe without locking. |
| Why is the workflow table protected by `ptable.lock`? | The workflow table is only accessed from process context (syscalls, scheduler, exit) which all already hold `ptable.lock`. Adding a separate lock would complicate locking and risk deadlock; reusing `ptable.lock` is correct and efficient. |
| What happens if a process calls `setworkflow` twice? | The second call returns `-1` immediately. A process can only join one workflow for its lifetime. This simplifies accounting and prevents deadline manipulation. |
| Can donation pass through `wait()`? | No. Stage 5 follows only `waiting_pipe` edges. Supporting `wait()` would require an explicit parent/child wait edge and the same cycle-safe traversal. |
| Where should the cycle check move if the graph is represented differently? | It belongs at edge traversal, before descending into a node already marked gray; moving it after descent would recurse indefinitely. |
| Why not keep a donor list on each pipe? | A descriptor-table scan sees duplicated descriptors and the actual current holders. A writer pointer can be null at the first block and can dangle after close. |
| How does `fork()` handle scheduling fields? | The child inherits `wid` and `deadline` from the parent, but `donated` is reset to `NO_DEADLINE` (donations are not inherited), `last_run` and `missed` are reset to 0. |
| Why does `schedctl` use `setsched` syscall instead of writing to a file? | Syscalls are the xv6 mechanism for kernel interaction. A syscall ensures atomic policy change and proper privilege checking. |
| Why is the Python validator not the security boundary? | It runs outside xv6 and can be bypassed, replaced, or buggy. It reduces accidental and prompt-injection traffic, but the kernel must independently enforce admission, scheduling, and resource limits. |
| What happens if the host validator is bypassed? | A direct xv6 command still passes through kernel admission control. The kernel rejects deadlines below `MIN_SLACK` and urgent-process counts above `MAX_URGENT`, updates counters, and logs the rejection after releasing `ptable.lock`. |
| How do you add a new trace event? | Define a new `TRACE_*` constant in `sched_api.h`, then call `trace_event(cpuid(), pid, TRACE_NEW_EVENT, arg)` from the relevant kernel location while holding `ptable.lock`. |
| Where do trace timestamps come from? | The `rdtsc()` instruction reads the CPU's Time-Stamp Counter (64-bit), split into `tlo` (low 32 bits) and `thi` (high 32 bits). This provides cycle-accurate timestamps independent of the `ticks` counter. |
| Why use `rdtsc` instead of `ticks` for tracing? | `ticks` has ~10ms resolution and only increments on CPU 0; `rdtsc` provides ~1ns resolution on all CPUs and captures exact context-switch timing. |
| How does the trace ring handle wrap-around? | When `trace_head[cpu]` reaches `TRACE_SIZE`, new entries overwrite the oldest. The global `seq` counter monotonically increases, so gaps in sequence numbers indicate wrapped entries. |
| What does `schedtrace` return? | It copies up to `max` entries total, oldest-first within each CPU, and returns the number copied across all CPUs. |
| How does the harness handle QEMU crashes? | Each run uses `-snapshot` for isolation. On panic/timeout, the harness records a failure row with `status=panic` or `status=timeout` and continues to the next cell. |
| Why is `trace_seq` global rather than per-CPU? | A global sequence counter provides a total ordering of events across all CPUs, enabling correct reconstruction of the global event timeline from per-CPU rings. |
| Explain this graph: `misses_bar.png` | It shows the miss rate (finish > deadline, computed by wfgen and checked by the harness) at α 1.5, deadline 72, for rr, edf and edf_donate on CPUS=1 and CPUS=3, with 95% percentile bootstrap error bars and n = 20 per bar. On CPUS=1 rr and edf missed 20/20 and edf_donate 0/20 (Fisher edf vs edf_donate p = 1.451e-11). On CPUS=3 every policy missed 0/20 (p = 1), so the pattern is weaker, as predicted. Every bar has a point interval because each cell has 0 or n misses, where the bootstrap collapses. |
| Explain this graph: `miss_vs_alpha.png` | It shows the CPUS=1 miss rate against α, where deadline = round(α × W) with W = 48.2 (deadlines 58, 72, 96, 145), one line per policy, 10 runs per cell (20 at α 1.5) and bootstrap error bars. edf_donate misses 0 at every α from 1.2. rr and edf miss every run at α 1.2 and 1.5; at α 2.0 rr misses 0/10 and edf 1/10; at α 3.0 no policy misses. rr's mean finish at α 3.0 (93.1 against 87.0 to 89.0) is treated as TCG noise, since rr never reads the deadline (L-37). |
| Explain this graph: `finish_box.png` | It shows the finish-time distribution of each policy at α 1.5 for CPUS=1 and CPUS=3, 20 runs per box, with a dashed line at the 72-tick deadline. On CPUS=1 the rr and edf boxes lie above the line (means 87.05 and 87.4) and edf_donate lies below it (mean 49.1, median 48), essentially the unloaded time W = 48.2. On CPUS=3 all three boxes lie below the line (means 53.65 for rr, 60.25 for edf, 57.35 for edf_donate); one edf run finished exactly at 72 and counts as met, because a miss is finish > deadline. |
| Explain this graph: `gantt-T57-edf.png` | It is the edf trace of `wfgen 4 100 2048 72 3` on CPUS=1: one lane, one bar colour per PID. The run finished at 90 ticks against a deadline of 72. The ring wrapped, so the chart holds 256 events from seq 37. The `wfgen` parent is PID 7, the hogs are PIDs 8-10 and the stages 11-14 (14 is the final stage). The hogs and stages 1-3 take equal turns, so the upstream stages are slowed rather than starved, because none of them has a deadline; DEADLINE_MISS on PID 14 appears at seq 219. The x-axis is the trace sequence number, not ticks. |
| Explain this graph: `gantt-T58-edf_donate.png` | It is the edf_donate trace of the same workload, from a run that finished at 45 ticks. The ring wrapped, so the chart holds 256 events from seq 321. The PID roles are the same as in T-57. From seq 321 to about 531 only stages 11-14 run, with DONATE (ev 3) and WITHDRAW (ev 4) markers carrying deadline 3093; the hogs 8-10 run only afterwards. This is donation passing the final stage's deadline upstream through the pipes. |

## One-page cheat sheet

| Topic | Code-grounded answer |
|---|---|
| Effective priority | `effective(p)` returns the earlier of `p->deadline` and `p->donated`; `NO_DEADLINE` is treated as latest ([proc.c:123](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:123)). |
| Two deadline fields | `deadline` is the process-owned workflow deadline; `donated` is temporary inherited urgency. `fork()` copies the owned deadline but clears donation ([proc.c:814](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:814)). |
| Wraparound and tie-break | `dl_before()` uses signed modular subtraction and handles `NO_DEADLINE` first ([proc.c:106](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:106)); scheduler selection compares effective deadlines, then least-recently-run `last_run` ([proc.c:990](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:990)). |
| Pipe edges | A blocked writer records `waiting_pipe`; donation scans descriptors and only follows a process holding that pipe's write end ([proc.c:187](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:187), [proc.c:290](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:290)). |
| Lock order | Existing paths establish `tickslock -> ptable.lock`, `cons.lock -> ptable.lock`, and `pipe->lock -> ptable.lock`; therefore diagnostic printing while holding `ptable.lock` can deadlock through console locking. Diagnostics are deferred and printed after unlock ([proc.c:232](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:232)). |
| Withdrawal termination | `recompute_donations_locked()` repeatedly applies changes until a pass makes no change, so finite process and descriptor tables provide a bounded fixpoint ([proc.c:248](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:248)). |
| Cycle handling | Donation traversal marks the active path and reports a cycle before descending again; the report is deduplicated for the active traversal ([proc.c:203](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:203)). |
| Admission and firm deadlines | `sys_setworkflow_impl()` rejects slack below `MIN_SLACK` and admissions beyond `MAX_URGENT`; scheduler miss handling removes the deadline and increments the miss count ([proc.c:431](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:431), [proc.c:330](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:330)). |
| Validator boundary | `validate_action()` checks host request shape and configured bounds, but a user can bypass the host and type a guest command; kernel admission remains authoritative ([validator.py:21](/home/ridham-shah/Desktop/kernelkraft/host/validator.py:21), [proc.c:431](/home/ridham-shah/Desktop/kernelkraft/xv6-public/proc.c:431)). |
| Limits | The model leaves out donation through `wait()`, fine-grained locking, unlimited trace history, and utilization-based admission; these are recorded in [LIMITATIONS.md](/home/ridham-shah/Desktop/kernelkraft/docs/LIMITATIONS.md). |

## Viva drills

1. **Donation through `wait()`**
   Files: `xv6-public/proc.c`, `xv6-public/proc.h`, `docs/DESIGN.md`.
   Add an explicit parent-wait edge, traverse it with the same cycle guard, and clear it on wake/exit.
   Add a two-process regression and verify no donation remains after the child exits.

2. **FIFO tie-break**
   Files: `xv6-public/proc.c`, `xv6-public/sched_api.h`, `xv6-public/edftest.c`.
   Replace the `last_run` comparison with a documented FIFO sequence field.
   Run equal-deadline children and assert creation order without changing deadline ordering.

3. **Move the cycle check**
   Files: `xv6-public/proc.c`, `xv6-public/cycletest.c`.
   Keep the gray-path check immediately before following an edge.
   Move it after recursion only as a negative experiment, then restore it after demonstrating the recursion failure.

4. **Add a `sched_stats` counter**
   Files: `xv6-public/sched_api.h`, `xv6-public/proc.c`, `xv6-public/sysproc.c`, `xv6-public/schedstat.c`.
   Add one field to the shared result structure and increment it at the single event site.
   Print it from the existing syscall and add a stable user-level assertion.

5. **Change `MIN_SLACK`**
   Files: `xv6-public/sched_params.h`, `host/config.json`, `host/tests/test_validator.py`, `docs/PARAMS.md`.
   Change the parameter in both authoritative configuration files.
   Update boundary tests and confirm both host rejection and kernel rejection agree.

6. **Donation depth cap K**
   Files: `xv6-public/sched_params.h`, `xv6-public/proc.c`, `xv6-public/donate5.c`.
   Add a depth counter to traversal and stop propagation after K edges while retaining cycle detection.
   Test a chain longer than K and verify the receiver still gets the nearest donation.

7. **New trace event**
   Files: `xv6-public/sched_api.h`, `xv6-public/proc.c`, `xv6-public/schedtrace.c`, `docs/SYSCALLS.md`.
   Reserve an event number and emit it only while `ptable.lock` is held.
   Extend the parser/fixture and assert the event survives ring wrap.

8. **Validator clamp versus reject**
   Files: `host/validator.py`, `host/config.json`, `host/tests/test_validator.py`, `docs/LIMITATIONS.md`.
   Select one policy explicitly and make the result visible in the audit record.
   Test below-minimum and above-maximum values plus a benign boundary value; never rely on the validator as kernel enforcement.

## Test inventory cross-check

The host inventory is covered by `host/tests/test_validator.py`, `test_stage7_harness.py`,
`test_adaptive_planner.py`, `test_stage7_analyze.py`, `test_index_evidence.py`, and
`test_w_ticks_refusal.py`. The corresponding rows are T-15--T-26, T-50--T-60, and
T-61--T-65. The user-program inventory is the `UPROGS` list in
`xv6-public/Makefile`; its scheduler, donation, trace, calibration, and workload
programs are represented by T-01, T-06--T-13, T-34--T-49, and T-54--T-60.
No executable in those inventories is omitted from the final table; historical
raw logs that were not retained are explicitly identified in `EVIDENCE_INDEX.md`.
