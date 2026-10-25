# Design

## Reading notes

- **Scheduler and switching:** `scheduler()` enables interrupts, acquires
  `ptable.lock`, scans for `RUNNABLE` processes, and calls `swtch()` to the
  selected process. The process must release and reacquire `ptable.lock`
  before switching back; the scheduler releases it after the scan
  ([proc.c](../xv6-public/proc.c)).
- **Sleep and wakeup:** `sleep(chan, lk)` acquires `ptable.lock` before
  releasing a different lock, marks the caller `SLEEPING`, enters `sched()`,
  then reacquires the original lock after wakeup. `wakeup1()` changes matching
  sleepers to `RUNNABLE` while `ptable.lock` is held; `wakeup()` supplies that
  lock ([proc.c](../xv6-public/proc.c)).
- **Pipe blocking:** `pipewrite()` waits while the ring is full by sleeping on
  `&p->nwrite`; `piperead()` waits while empty and open by sleeping on
  `&p->nread`. Readers wake writers after consuming data, writers wake readers
  after producing data, and `pipeclose()` wakes the opposite side on close
  ([pipe.c](../xv6-public/pipe.c)).
- **Timer and ticks:** `lapicinit()` programs each local APIC timer in periodic
  mode with initial count `10000000` ([lapic.c](../xv6-public/lapic.c)).
  The timer trap increments `ticks` and wakes its waiters only when
  `cpuid() == 0`, preventing multiple CPUs from counting the same clock
  ([trap.c](../xv6-public/trap.c)).
- **Shell pipelines:** `runcmd()` creates one pipe, forks the left child and
  maps its stdout to the pipe write end, then forks the right child and maps
  its stdin to the pipe read end. Each child closes both unused descriptors;
  the shell parent closes both descriptors and waits for both children
  ([sh.c](../xv6-public/sh.c)).

## Stage 0 scope

This stage records the existing design only. No kernel scheduling or pipe
logic is changed.

## Capacity

The original `FSSIZE` was 1000 blocks. Stage 1 raises it to 4000 blocks so
the filesystem image has room for the additional user programs and regression
tests. Because the Makefile does not infer filesystem-image layout changes
from `param.h`, run `make clean` before rebuilding.

## Clock

The Stage 1 `ticktest` recorded a 500-tick difference over 5.106 seconds,
giving an observed rate of approximately 97.9 ticks per second. This
measurement is empirical; the LAPIC initial count alone does not establish
wall-clock frequency.

## Bridge

`host/bridge/qemu_bridge.py` drives the xv6 serial console with `pexpect`.
It waits for `init: starting sh` and then the `$ ` shell prompt, logs all
received bytes to a timestamped raw file, and removes the echoed command and
carriage returns from `run_raw()` results. Guest command lines must be fewer
than 90 characters. The bridge uses a 120-second startup timeout and a
per-command timeout of 15 seconds by default.

## Stage 2: Scheduler

### Overview

Stage 2 introduces a runtime-switchable scheduler with three policies:
- **Policy 0 (RR):** Original round-robin scheduler (unchanged)
- **Policy 1 (EDF):** Earliest Deadline First scheduling
- **Policy 2 (EDF+Donate):** EDF with priority donation (stubbed for Stage 3)

The scheduler policy is controlled via the `setsched(int)` system call (syscall 24).
The current policy and statistics can be queried via `schedinfo()` (syscall 26).

### Effective Deadline

Each process has two deadline fields:
- `deadline`: The process's own absolute deadline (set via `setworkflow`)
- `donated`: A donated deadline from priority donation (initially `NO_DEADLINE`)

The **effective deadline** of a process is the more urgent (earlier) of the two:

```c
static uint effective(struct proc *p) {
    uint d = p->deadline;
    if (p->donated != NO_DEADLINE && dl_before(p->donated, d))
        return p->donated;
    return d;
}
```

This allows a process to temporarily run with an earlier deadline when it
holds a resource needed by a more urgent process (priority donation).

### Deadline Comparison with Wrap-around

The `ticks` counter is a 32-bit unsigned integer that wraps around. Comparing
deadlines using plain `<` is incorrect because after wrap-around, a later
deadline could appear numerically smaller.

The `dl_before(a, b)` function uses signed subtraction to handle wrap-around:

```c
static int dl_before(uint a, uint b) {
    return (int)(a - b) < 0;
}
```

**Worked example:** Suppose `ticks = 0xFFFFFF00` (near wrap). Process A has
deadline `0xFFFFFF10` (16 ticks from now), Process B has deadline `0x00000020`
(32 ticks from now, but appears smaller after wrap). 

- `a - b = 0xFFFFFF10 - 0x00000020 = 0xFFFFFFF0` (signed: -16)
- `(int)(a - b) < 0` is true, so A is correctly determined to be before B.

### Scheduler Algorithm (Policies 1 and 2)

For EDF policies, the scheduler scans all `NPROC` slots while holding
`ptable.lock`, selecting the `RUNNABLE` process with the earliest effective
deadline:

```c
for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
    if(p->state != RUNNABLE) continue;
    if (best == 0) best = p;
    else {
        uint eff_p = effective(p);
        uint eff_best = effective(best);
        if (dl_before(eff_p, eff_best)) best = p;
        else if (eff_p == eff_best && p->last_run < best->last_run) best = p;
    }
}
```

**Tie-breaking:** When two processes have equal effective deadlines, the
process with the smaller `last_run` value (least recently run) is chosen.
Using `<` (not `<=`) ensures strict ordering and prevents index starvation
where a lower-index process would always win ties.

### Workflows

A **workflow** is a group of processes sharing a common absolute deadline.
Workflows are identified by a workflow ID (`wid`) in range `1..NWF-1` (where
`NWF=8` from `sched_params.h`). Workflow 0 means "no workflow".

The workflow table is defined in `proc.c` and protected by `ptable.lock`:

```c
struct workflow {
    int wid;             // Workflow ID (0 = unused)
    uint abs_deadline;   // Absolute deadline for this workflow
    int nmembers;        // Number of processes in this workflow
    int misses;          // Number of deadline misses
    int rejected;        // Number of rejected admissions
} workflows[NWF];
```

**`setworkflow(wid, deadline)`** (syscall 25):
- Validates `wid > 0 && wid < NWF` and `deadline > 0`
- Rejects if the calling process already has a workflow (`wid != 0`)
- First caller of a `wid` initializes `abs_deadline = now_ticks() + deadline`
- Subsequent callers with same `wid` must match the existing `abs_deadline`
- On success, sets `p->wid = wid` and `p->deadline = abs_deadline`

**`exit()`** calls `wf_leave_locked()` to decrement `nmembers`; when it
reaches zero, the workflow slot is freed.

### Locking

All workflow operations and scheduler scans execute with `ptable.lock` held.
The `now_ticks()` helper reads the global `ticks` variable without acquiring
`tickslock` (32-bit aligned read is atomic on x86), which is safe because
the scheduler already holds `ptable.lock` and we must never acquire
`tickslock` while holding `ptable.lock` (lock order: `tickslock -> ptable.lock`).

### Statistics

`schedinfo()` (syscall 26) fills a `struct sched_stats`:
- `policy`: Current scheduling policy (0, 1, or 2)
- `ncpu`: Number of CPUs (global `ncpu`)
- `ticks`: Current tick count (via `now_ticks()`)
- `misses`: Sum of `workflow.misses` across all workflows
- `donations`: Number of priority donations (0 in Stage 2)
- `cycles`: Scheduling cycle counter (`runcounter`)
- `rejected`: Sum of `workflow.rejected` across all workflows
