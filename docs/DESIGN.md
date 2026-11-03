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

## Stage 3: Agent trust boundaries

The planner proposes a structured tool call; it is not trusted input. The
validator checks the tool name, exact argument set, types, allowlist, and
configured bounds. The bridge accepts only validated values and expands them
through fixed command templates, so planner text is never typed as a guest
command. The kernel remains the final enforcement point for scheduling and
admission policy; a Python validator is a convenience boundary, not a security
boundary.

| Tool | Guest template | Policy |
|---|---|---|
| `list_files()` | `ls` | no arguments |
| `read_file(path)` | `cat <validated path>` | xv6-safe name and config allowlist |
| `set_policy(policy)` | `schedctl <validated enum>` | `rr`, `edf`, or `edf_donate` |
| `run_pipeline(...)` | `wfgen <validated integers>` | configured stage, slack, work, bytes, and hog bounds |
| `sched_stats()` | `schedstat` | no arguments |
| `summarize(text)` | host only | no guest effect |

## Stage 3: Sentinel protocol

The bridge sends `xrun <random nonce> <fixed command>`. `xrun` prints
`@@EXECFAIL <nonce>` when `exec` fails and prints `@@DONE <nonce>` after the
child has been waited for. The bridge verifies the echoed command and the
matching nonce, then waits for the next shell prompt. A panic, killed process,
or timeout is recorded as a non-success and causes a restart; completion is
never inferred from a timeout.

The session transcript is retained, and each `run()` invocation also tees
received console data into a unique `logs/*.run.raw` file for per-command
evidence.

`@@DONE` means that the guest process was reaped, not that its command was
semantically successful. The host marks known tool-level error output such as
`cat: cannot open ...` as `error` in the observation and audit record.
Audit records include `execution_source` (`qemu` or `fake`) so unit-test
evidence cannot be mistaken for serial-console evidence.

## Stage 4: Admission control and firm deadlines

The kernel is the second enforcement layer. `setworkflow` checks the relative
deadline against `MIN_SLACK` and counts live finite-deadline processes before
accepting another urgent process. Rejection updates workflow and global
counters, releases `ptable.lock`, and only then emits the `admit: rejected`
diagnostic. The scheduler marks each overdue finite-deadline process once;
missed processes use `NO_DEADLINE` for EDF selection, so late work becomes
best-effort. `exit` performs the same check before removing a process from its
workflow.

The injection demonstration has two layers: the host validator rejects the
deadline-1/8-hog proposal before QEMU traffic, while a user who bypasses the
host can type `wfgen 3 200 4096 1 8` at the xv6 prompt and reach kernel
admission control. The latter is the security boundary because the host is
outside the guest.

## Stage 2: Scheduler

## Stage 5: Pipe donation

Only policy 2 enables donation. A process is an over-approximate holder of a
pipe when a non-UNUSED process has an open writable `FD_PIPE` for that pipe in
its descriptor table. The scan intentionally reads `ofile` without another
lock; this is a documented benign race in the xv6 process model.

Immediately before a blocked `piperead()` sleeps, `pipe_wait_begin()` records
the process's `waiting_pipe` and, when it has a finite effective deadline,
performs an iterative DFS. Each frame contains a process, the propagated
deadline, and the next process-table slot to inspect. A white holder is
descended into, a black holder is skipped, and a gray holder records one cycle
event without descending. Both the explicit stack and traversal depth are
bounded by `NPROC`. `pipe_wait_end()` clears `waiting_pipe` and runs the
fixpoint recomputation.

Recomputation first clears all donated deadlines, then makes at most `NPROC+1`
monotone passes over waiting readers and writable holders. This withdraws
donations when a reader is killed or wakes while preserving donations from
other readers. `exit()` clears the exiting process's wait edge and invokes the
same recomputation while holding `ptable.lock`.

The lock path for the donation hook is `pipe->lock -> ptable.lock`: the pipe
lock is held by `piperead()` when the hook starts, and the hook acquires and
releases `ptable.lock` internally. No donation path acquires a pipe lock,
`cons.lock`, or `tickslock` while holding `ptable.lock`; diagnostics are stored
as small events and printed only after releasing it. `ticks` is read through
the existing unlocked, aligned read, and deadlines use wrap-safe signed
subtraction. A descriptor-table scan is used rather than a writer pointer
because shell-created descriptors can be duplicated and the pointer would be
unset or stale at a block boundary.

The empty donation sentinel requires an explicit check: because
`NO_DEADLINE` is `0xffffffff`, `dl_before(dl, NO_DEADLINE)` is not a valid
way to recognize an unset donation under modular subtraction.

### Overview

Stage 2 introduces a runtime-switchable scheduler with three policies:
- **Policy 0 (RR):** Original round-robin scheduler (unchanged)
- **Policy 1 (EDF):** Earliest Deadline First scheduling
- **Policy 2 (EDF+Donate):** EDF with pipe priority donation

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
- `cycles`: Pipe-donation cycle counter
- `rejected`: Sum of `workflow.rejected` across all workflows

## Stage 6: Workload Generator, Trace Ring, and Harness

### Workload Design (`wfgen`)

The `wfgen` (workflow generator) program creates multi-stage pipelines with configurable CPU-bound "hog" processes to stress-test the scheduler. It takes 5 parameters:

- `stages`: Number of pipeline stages (2-6)
- `work`: CPU work units per stage (busy-loop iterations)
- `bytes`: Total bytes to pass through the pipeline
- `deadline`: Relative deadline in ticks for the workflow
- `hogs`: Number of CPU-bound background processes

**Architecture:**
1. `hogs` background processes are forked first, each running an infinite `burn(work)` loop
2. Stage 1 (producer) writes `bytes` bytes to a pipe in chunks, doing `burn(work)` between writes
3. Stage 2 (consumer) calls `setworkflow(wid, deadline)`, reads from pipe doing `burn(work)` per chunk
4. Stages 2-6 are supported; each stage forwards the pipe data and performs its configured work
5. Parent waits for all children, kills hogs, and prints a single `RESULT` line with: policy, cpus, finish time, deadline, miss count

The `RESULT` line is built in a buffer and emitted with a single `write()` to avoid interleaving with other processes' output.

**Hygiene:** All file descriptors are properly closed in each process. Hog processes are killed and waited on to avoid zombies.

### Trace Ring

A per-CPU circular trace ring records scheduling events for offline analysis and visualization.

**Structure (in `proc.c`):**
```c
struct trace_ent {
    uint tlo;       // TSC low 32 bits (from rdtsc)
    uint thi;       // TSC high 32 bits (from rdtsc)
    short cpu;      // CPU ID (0..NCPU-1)
    short pid;      // Process ID
    short ev;       // Event type (TRACE_*)
    short pad;      // Padding for alignment
    int arg;        // Event-specific argument (deadline, etc.)
    uint seq;       // Global sequence number
};
static struct trace_ent trace_ring[NCPU][TRACE_SIZE];
static uint trace_head[NCPU];     // Next write index per CPU
static int trace_enabled = 1;     // Trace enabled by default
static uint trace_seq = 0;        // Global sequence counter
```

**Event Types:**
- `TRACE_SWITCH_IN` (1): Process starts running on CPU
- `TRACE_SWITCH_OUT` (2): Process stops running on CPU
- `TRACE_DONATE` (3): Priority donation occurred (donor -> receiver)
- `TRACE_WITHDRAW` (4): Donation withdrawn (receiver's donated cleared)
- `TRACE_CYCLE` (5): Donation cycle detected
- `TRACE_DEADLINE_MISS` (6): Process missed its deadline

**Locking:** All writers hold `ptable.lock`. The trace ring is updated while `ptable.lock` is held in:
- `scheduler()`: emits SWITCH_IN before `swtch()`, SWITCH_OUT after `swtch()`
- `donate_walk_locked()`: emits DONATE when deadline propagated, CYCLE when cycle detected
- `recompute_donations_locked()`: emits WITHDRAW when clearing donated deadlines
- `mark_missed_locked()`: emits DEADLINE_MISS when deadline missed

**Timestamp Source:** `rdtsc()` reads the CPU's Time-Stamp Counter (64-bit, split into `tlo`/`thi`). This provides high-resolution timestamps independent of the tick counter. The global `trace_seq` provides a total ordering across CPUs.

**Ring Wrap:** When `trace_head[cpu] >= TRACE_SIZE`, new entries overwrite oldest entries. The `seq` field allows detecting gaps.

**Syscall 29 (`schedtrace`):** Copies at most `max` entries total from all CPU rings to a validated user buffer, oldest-first within each CPU. The copy is performed while `ptable.lock` is held so ring slots cannot change.

**Syscall 27 (`tracectl`):** Controls tracing:
- 0: disable trace
- 1: enable trace
- 2: clear all rings (reset heads and seq)
- 3: enable donation debug prints (existing)
- 4: disable donation debug prints (existing)

### Host Harness (`run_all.py`)

The unattended test harness runs the full test matrix:
- Policies: `rr`, `edf`, `edf_donate`
- CPUs: 1, 3
- 20 runs per cell (2 for `--dry-run`)
- Restarts QEMU per run with `-snapshot` for isolation
- Parses strict `RESULT` regex from guest output
- Produces CSV with columns: `policy,cpus,run,alpha,finish,deadline,miss,status,commit_hash,rawlog_path`
- Resume support: skips already-completed cells
- Survives QEMU panic/timeout: records failure row and continues

### Gantt Plotter (`plot_gantt.py`)

Parses `schedtrace` output text, creates a Gantt chart:
- One lane per CPU
- Horizontal bar per process interval (SWITCH_IN to SWITCH_OUT)
- Vertical markers for DONATE (red), WITHDRAW (blue), CYCLE (yellow), DEADLINE_MISS (black)
- Outputs PNG for visual inspection of donation chains

### Calibration (`calib`)

Busy-loop calibration program to determine `work` units per tick:
- Runs `N` iterations of a standardized busy loop
- Prints `uptime()` delta
- Used to compute `W` (ticks per work unit) for workload sizing

Calibration and dry-run evidence are stored under `logs/` and `results.csv`.
The CPUS=3 portion remains blocked in this environment because xv6 reports only
one discovered CPU despite QEMU receiving `-smp 3`.
