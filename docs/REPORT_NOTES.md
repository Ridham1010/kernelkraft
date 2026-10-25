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

## Donation and proofs

## Security

## Results

## Problems

## Limits

