# Report notes

<!-- Model (120 words) -->
## Model

The scheduler supports three policies selectable at runtime via `setsched()`:
- **RR (0)**: Original round-robin, each RUNNABLE process runs in turn.
- **EDF (1)**: Earliest Deadline First. Each process has an absolute deadline.
  The scheduler picks the RUNNABLE process with the earliest effective deadline.
  Effective deadline is the more urgent of the process's own deadline and any
  donated deadline. Deadlines are compared with `dl_before(a,b)` using signed
  subtraction to handle 32-bit `ticks` wrap-around correctly.
- **EDF+Donate (2)**: Same as EDF for Stage 2; priority donation is planned
  for the later kernel/donation stages and is not implemented here.

Processes join workflows via `setworkflow(wid, relative_deadline)`. The first
caller of a workflow ID establishes the absolute deadline as `now_ticks() +
relative_deadline`. All members of a workflow share this absolute deadline.

Preemption occurs on each timer tick: the interrupt handler calls `yield()`
which returns to the scheduler, which re-evaluates the best process under
the current policy. The tie-break on equal effective deadlines uses
`last_run` (monotonic counter) with `<` (not `<=`) to avoid index starvation.

## Locking

The existing global order is `tickslock -> ptable.lock`,
`cons.lock -> ptable.lock`, and `pipe->lock -> ptable.lock` through
`sleep()`. Donation hooks follow only the last order: `piperead()` already
holds the pipe lock, then `pipe_wait_begin/end()` acquire and release
`ptable.lock`. They never acquire a pipe lock, `cons.lock`, or `tickslock`
under `ptable.lock`; event records defer `cprintf()` until after release.
The scheduler's unlocked 32-bit `ticks` read is atomic on x86.

## Donation and proofs

The DFS uses an explicit stack and white/gray/black colours, so every
reachable process is bounded by `NPROC`; a gray edge reports a cycle and is
not followed. Recompute terminates because each of its finite `NPROC+1`
rounds only makes deadlines more urgent, and the finite deadline set reaches
a fixed point. On the next invocation it resets and recomputes from current
wait edges, which withdraws stale donations. A scan beats a writer pointer:
the shell can duplicate pipe descriptors, the pointer is unavailable at the
first block, and ownership can change as descriptors close.

The empty donation sentinel is checked explicitly because
`dl_before(dl, NO_DEADLINE)` is false for ordinary deadlines when
`NO_DEADLINE` is `0xffffffff`.
Superseded in Stage 7 (305a13f): dl_before now treats NO_DEADLINE as latest,
so dl_before(dl, NO_DEADLINE) is true for any real deadline; see DESIGN.md
Stage 7.

## Security

Stage 4 has two enforcement layers. The Python validator rejects malformed,
disallowed, or out-of-range planner actions before they become QEMU commands.
The kernel admission check is the security boundary: it independently enforces
`MIN_SLACK` and `MAX_URGENT`, records rejection, and emits an admission
diagnostic after releasing `ptable.lock`. The second layer matters because a
user can bypass the host agent and type a command directly at the xv6 shell.

## Results

<!-- Stage 7 Results (150 words) -->
Stage 7 ran `wfgen 4 100 1024` with W = 24.4 ticks and deadline
round(1.5 W) = 37; a miss is finish > deadline, computed on the host. On
CPUS=1 with 3 hogs, rr and edf missed 20/20 and edf_donate 1/20 (Fisher edf
vs edf_donate p = 3.0e-10); `misses_bar.png` shows these rates with 95%
bootstrap intervals. On CPUS=3 with 5 hogs prediction 2 was partly wrong:
rr 0/20, edf 7/20, edf_donate 1/20 (p = 0.0436). A hypothesis only: edf's
least-recently-run tie-break among `NO_DEADLINE` processes treats pipeline
stages and hogs equally. `miss_vs_alpha.png` shows the CPUS=1 sweep:
edf_donate misses 10/10 at α 1.0 and 0/10 from α 1.25, while rr reaches 0
only at α 3.0; edf's 4/10 at α 3.0 is attributed to run-order drift after
an order check. `gantt-T58-edf_donate.png` shows the mechanism: from seq 163
to about 308 only pipeline stages run, each preceded by a DONATE marker,
and the hogs run afterwards.

## Problems

<!-- Stage 7 Problems (80 words) -->
The pilot showed edf and edf_donate finishing about 30 ticks after the
deadline. `dl_before` computed `(int)(a - b) < 0`, so `NO_DEADLINE`
(`0xffffffff`) acted as -1 and `effective()` ignored donations to stages
without their own deadline; 305a13f treats `NO_DEADLINE` as latest. xv6 saw
one CPU under `-smp 3` because the default machine's MP table lists one
processor; `-machine pc-i440fx-yakkety` fixes this. The kernel miss counter
is cumulative per boot, so misses are computed on the host.

## Limits

Stage 7 limits are recorded in `LIMITATIONS.md`: L-24 is resolved by the
machine flag, and L-25 to L-34 cover small n and collapsed intervals, TCG
noise and run-order drift, the outliers, the concreate hang, the missing
CPUS=3 donation log, trace ring wrap, the kernel miss counter, the adaptive
agent's machine type, the Gantt x-axis, and the test that writes into
`logs/`.

## Stage 6: Trace and Workload

The trace ring provides a lightweight, per-CPU circular buffer for recording scheduling events. Each entry captures the TSC timestamp (via `rdtsc`), CPU ID, process ID, event type, argument, and a global sequence number. The ring is written while holding `ptable.lock` by the scheduler (context switches), donation code (DONATE, WITHDRAW, CYCLE), and deadline miss detection.

The `schedtrace` syscall (29) reads the rings and copies entries to a user buffer, oldest-first per CPU. The `tracectl` syscall (27) controls tracing: enable/disable, clear, and donation debug prints.

The `wfgen` workload generator creates multi-stage pipelines with configurable hog processes. It prints a single `RESULT` line with structured output for automated parsing. The `calib` program measures busy-loop iterations per tick for workload sizing.

The host harness (`run_all.py`) runs the full test matrix (policies × CPUs × runs) with QEMU snapshot isolation, CSV output, and resume support. The Gantt plotter (`plot_gantt.py`) visualizes trace data with donation markers.
