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

## Security

Stage 4 has two enforcement layers. The Python validator rejects malformed,
disallowed, or out-of-range planner actions before they become QEMU commands.
The kernel admission check is the security boundary: it independently enforces
`MIN_SLACK` and `MAX_URGENT`, records rejection, and emits an admission
diagnostic after releasing `ptable.lock`. The second layer matters because a
user can bypass the host agent and type a command directly at the xv6 shell.

## Results

## Problems

## Limits
