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
The PLAN-conformant batch ran `wfgen 4 100 2048` with W = 48.2 ticks and
deadline round(1.5 W) = 72. wfgen reports miss = finish > deadline and the
harness checks it; all 210 runs were ok. On CPUS=1 with 3 hogs, rr and edf
missed 20/20 and edf_donate 0/20 (Fisher edf vs edf_donate p = 1.5e-11).
`finish_box.png` shows rr and edf finishing at about 87 ticks, above the
deadline line, and edf_donate at a mean of 49.1, close to W. On CPUS=3 with
5 hogs every policy met all 20 deadlines (p = 1). `miss_vs_alpha.png` shows
the CPUS=1 sweep: edf_donate meets every deadline from α 1.2, while rr and
edf miss every run at α 1.2 and 1.5 and meet it from α 2.0, apart from one
edf run. `gantt-T58-edf_donate.png` shows the mechanism: from seq 321 to
about 531 only pipeline stages run, with DONATE markers, and the hogs run
afterwards.

## Problems

<!-- Stage 7 Problems (80 words) -->
The first pilot showed edf and edf_donate finishing about 30 ticks after
the deadline. `dl_before` computed `(int)(a - b) < 0`, so `NO_DEADLINE`
acted as -1; 305a13f treats it as the latest value. xv6 saw one CPU under
`-smp 3` until `-machine pc-i440fx-yakkety` was passed. The first batch did
not match PLAN (bytes 1024, cumulative kernel miss counter, clock started
before the hogs), so 066060f aligned the code and the batch was rerun. The
first batch is archived in `results/archive_v1/`.

## Limits

Stage 7 limits are recorded in `LIMITATIONS.md`: L-24 is resolved by the
machine flag and L-31 (kernel miss counter) by 066060f. L-25, L-26, L-27 and
L-30 describe the archived first batch. L-28, L-29 and L-32 to L-34 cover
the concreate hang, the missing CPUS=3 donation log, the adaptive agent's
machine type, the Gantt x-axis and the test that writes into `logs/`.
L-35 to L-39 cover the second batch: small n and collapsed intervals, the
wrapped Gantt rings, rr drift at α 3.0, PLAN's T_RR overestimate, and the
absent author headers.

## Stage 6: Trace and Workload

The trace ring provides a lightweight, per-CPU circular buffer for recording scheduling events. Each entry captures the TSC timestamp (via `rdtsc`), CPU ID, process ID, event type, argument, and a global sequence number. The ring is written while holding `ptable.lock` by the scheduler (context switches), donation code (DONATE, WITHDRAW, CYCLE), and deadline miss detection.

The `schedtrace` syscall (29) reads the rings and copies entries to a user buffer, oldest-first per CPU. The `tracectl` syscall (27) controls tracing: enable/disable, clear, and donation debug prints.

The `wfgen` workload generator creates multi-stage pipelines with configurable hog processes. It prints a single `RESULT` line with structured output for automated parsing. The `calib` program measures busy-loop iterations per tick for workload sizing.

The host harness (`run_all.py`) runs the full test matrix (policies × CPUs × runs) with QEMU snapshot isolation, CSV output, and resume support. The Gantt plotter (`plot_gantt.py`) visualizes trace data with donation markers.
