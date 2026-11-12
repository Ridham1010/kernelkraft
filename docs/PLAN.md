# Project 3: Deadline Scheduler with Priority Donation and an Injection-Resistant Agent

**Course:** CSL3030 Operating Systems Lab, IIT Jodhpur
**Team:** KernelKraft
**Platform:** xv6-public (x86, 32-bit) from the course tarball `cs236-xv6-linux.tgz`, running in QEMU
**Duration:** 20 days in two parts (Days 1-10 and Days 11-20)
---

## 1. Objective and scope

The handout asks for an EDF scheduler with priority donation through pipes. The agent guide asks for a host-side Python agent that drives xv6 through a QEMU bridge. We build them as one system: the agent plans and launches deadline-bound pipeline workflows on xv6, observes whether they met their deadlines, and adapts its choice of policy. Fairness and the refusal of abusive deadline requests are the kernel's job, and the kernel keeps doing that job when the agent has been prompt-injected.

The project has to demonstrate three results at the viva:

1. **Kernel.** On pipeline workloads competing with CPU hogs, EDF with transitive donation misses fewer deadlines than round-robin and than EDF alone.
2. **Agent.** A closed loop over a real guest OS: pilot run, measure, change policy, rerun, with every step logged.
3. **Security.** An injected agent that asks for a deadline-1 pipeline with 8 hogs is stopped by the tool validator, and the same command typed directly at the xv6 shell is stopped by the kernel.

### 1.1 Features beyond the handout minimum

| Feature | Purpose |
|---|---|
| Runtime-switchable policy (`rr`, `edf`, `edf_donate`) through `setsched()` | One kernel binary produces all three data sets, so comparisons are not confounded by different builds. |
| Pipe writer discovery by scanning fd tables | A shell-built pipeline has no single writer to point at. The scan finds every process holding the write end. |
| Donation withdrawal by full recompute to a fixpoint | One mechanism covers multiple donors, chains and cycles. |
| Per-CPU trace ring with `rdtsc` timestamps and a Gantt plot | Shows the donation chain on a timeline. Ticks are too coarse for this. |
| Admission control and firm deadlines | Refuses deadline abuse and stops an overdue job from monopolising the CPU (the EDF domino effect). |
| Adaptive planner | The agent uses measured misses to choose a policy. |
| Injection demonstration with a manual shell bypass | Shows that enforcement sits in the kernel and does not depend on the validator. |
| Slack sweep (miss rate against deadline slack α) | Shows the range of deadlines in which donation matters. |
| Deterministic boots with QEMU `-snapshot` | Every run starts from an identical disk. |
| Stretch: donation through `wait()` | Shows that the mechanism is not specific to pipes. |

### 1.2 Cut order

If the Day-10 checkpoint (Section 5, Stage 4) is not met, we cut scope that day in this order: the Ollama planner first, then donation through `wait()`. The deterministic planner, EDF and the pipe donation core are not negotiable.

---

## 2. Platform constraints

These properties of the course tree shape the design. Each one is verified against the source during Stage 0 before we rely on it.

| Area | Fact in this tree | Consequence for us |
|---|---|---|
| Compiler | `-m32 -Wall -Werror` | Any warning breaks the build. Use `0` in place of `NULL`. The kernel has no `stdint.h`, `bool` or 64-bit integer types, so we use `uint`. |
| Kernel printing | `cprintf()` supports only `%d %x %p %s %c %%` | Unsigned values are printed with `%x`. |
| User programs | `printf(1, ...)` takes the fd first. `exit()` and `wait()` take no status. | Guest tools report success or failure in their own output. |
| User `printf` | Writes one character per `write()` call | Output from concurrent processes interleaves. A line that must stay intact is built in a buffer and emitted with a single `write()`. |
| Adding a syscall | Number in `syscall.h`, prototype in `user.h`, `SYSCALL(name)` in `usys.S`, extern and table entry in `syscall.c`, implementation in `sysproc.c` | Number 22 is `hello`. Ours start at 23 and are registered in `docs/SYSCALLS.md`. |
| Syscall arguments | Passed on the user stack, read with `argint`, `argptr`, `argstr`, each returning -1 on failure | Every return value is checked. The kernel never writes through a user pointer that has not passed `argptr`. |
| Process table | One global `ptable.lock`. The `ptable` struct is anonymous inside `proc.c`. | All code that scans the process table lives in `proc.c`. |
| Sleep and wakeup | Classic `sleep(chan, lk)` and `wakeup(chan)` | Wait conditions are re-checked in a loop. |
| Clock | Only CPU 0 increments `ticks`, a 32-bit `uint` that wraps | Deadlines are compared with `(int)(a - b) < 0`, never with plain `<`. |
| Fine timestamps | None available | We add an `rdtsc()` inline function to `x86.h`. |
| Disk | `FSSIZE` is 1000 blocks (about 940 usable), and the stock programs already use about 600 | Raise `FSSIZE` to 4000. The Makefile does not track `param.h` for `fs.img`, so `make clean` is required after the change. |
| Shell | `sh.c` reads at most 99 characters per line | Guest command lines stay under 90 characters. |
| Build and run | `make qemu-nox CPUS=1`, plus `QEMU=/path/qemu-system-i386` if QEMU was built from source. Quit with Ctrl-A then X. | The exact launch line is fixed in Stage 1 and recorded in `docs/bridge.md`. |
| Debugging | `make qemu-nox-gdb`, then `gdb -x .gdbinit kernel` | If GDB refuses to load `.gdbinit`, add `set auto-load safe-path /` to `~/.gdbinit`. |
| Adding programs | `_name\` in `UPROGS` and `name.c` in `EXTRA`. Kernel files go in `OBJS` with shared functions declared in `defs.h`. | |

---

## 3. Architecture

```
HOST (Ubuntu)                                   GUEST (xv6-public i386 in QEMU)
┌────────────────────────────────────┐          ┌──────────────────────────────┐
│ Planner (rules, later Ollama)      │          │ user: xrun, wfgen, schedctl, │
│        │ JSON tool call            │          │  schedstat, schedtrace, tests│
│ Validator (schema, range, policy)  │ serial   │            │ syscalls (int 64)│
│        │ validated action          │ console  │ kernel: EDF + donation +     │
│ Bridge (pexpect, sentinels, logs)──┼──────────┼─► admission control + trace  │
│        │ observation               │          └──────────────────────────────┘
│ Audit log (JSONL) + plots          │
└────────────────────────────────────┘
```

There are four trust boundaries. The planner only proposes a structured tool call. The validator accepts it only if the tool is registered and every argument is of the right type and in range. The bridge then types a fixed command template into the guest with nothing but validated integers and enum values filled in, so text produced by a model never reaches the xv6 shell. Finally, the kernel applies admission control to every `setworkflow` call regardless of who issued it. The first three layers are conveniences that keep the agent well behaved. Only the last one is a security boundary, and the Stage 4 demonstration exists to show that.

---

## 4. Design

### 4.1 Scheduler

In the stock kernel each CPU runs `scheduler()` forever: enable interrupts, take `ptable.lock`, walk the 64-slot table and give every `RUNNABLE` process one quantum. The lock is held across `swtch` and released by the process itself in `yield`, `sleep` or `forkret`. Policy 0 (`rr`) keeps this loop unmodified.

For policy 1 (`edf`) and policy 2 (`edf_donate`) the same walk selects a single best candidate and runs only that one. The lock is held from the scan through the `swtch`, exactly as in the stock code. Since every timer interrupt already calls `yield()`, the choice is remade every tick and a newly urgent process preempts within one tick.

New fields in `struct proc`:

| Field | Meaning | Initial value |
|---|---|---|
| `int wid` | Workflow the process belongs to | 0 |
| `uint deadline` | Own absolute deadline in ticks | `NO_DEADLINE` |
| `uint donated` | Most urgent deadline lent by a waiter | `NO_DEADLINE` |
| `struct pipe *waiting_pipe` | Pipe the process is blocked reading, if any | 0 |
| `uint last_run` | Value of the run counter when last scheduled | 0 |
| `int missed` | Set once the own deadline has been missed | 0 |

`fork` copies `wid` and `deadline` and starts the child with `donated = NO_DEADLINE`. `exec` leaves all of them alone.

The own deadline and the donated deadline are separate fields so that a donation can be withdrawn without losing the process's own deadline. The scheduler ranks processes by `effective(p)`, the more urgent of the two. Comparison is wrap-safe:

```c
static int dl_before(uint a, uint b){   // true if a is more urgent than b
  if(a == NO_DEADLINE) return 0;
  if(b == NO_DEADLINE) return 1;
  return (int)(a - b) < 0;
}
```

Ties need care. With a strict `<` and many processes at `NO_DEADLINE`, the lowest table index always wins and high-index processes (often `sh`) starve behind a hog. Switching to `<=` only moves the starvation to the highest index. We break ties on the smallest `last_run` and set `last_run = ++runcounter` on every dispatch, which gives least-recently-run order among equals.

Code that holds `ptable.lock` reads the time through `now_ticks()`, an unlocked volatile load of `ticks`. A 32-bit aligned read is atomic on x86, and taking `tickslock` at that point would invert the lock order (Section 4.4).

### 4.2 Workflows, admission control and firm deadlines

A table `workflows[NWF]` in `proc.c`, protected by `ptable.lock`, holds `wid`, `abs_deadline`, `nmembers`, `misses` and `rejected` for each workflow. `setworkflow(wid, deadline_ticks)` works as follows. The first caller for a `wid` fixes `abs_deadline = now + deadline_ticks`, and later callers join that deadline. The call returns -1 for a non-positive `wid` or deadline, for a second call by the same process, and when the table is full. A process leaves its workflow in `exit()`, and the slot is freed when `nmembers` reaches zero so that the table does not fill up over a long agent session. Because a forked child inherits `wid`, `fork` increments `nmembers` to keep the decrement in `exit()` balanced.

**Admission control.** `setworkflow` rejects a request when `deadline_ticks < MIN_SLACK`, or when granting it would push the number of live processes with a finite deadline above `MAX_URGENT`. A rejection returns -1, increments the `rejected` counters, and prints one line after `ptable.lock` has been released:

```
admit: rejected pid=%d wid=%d deadline=%d reason=slack|urgent
```

**Firm deadlines.** During every scheduler scan, a process whose own deadline is overdue (`(int)(now - deadline) > 0`) is counted as a miss exactly once (the `missed` flag, the workflow counter and the global counter), and from then on `effective()` ignores its own deadline. Without this rule an overdue process holds the earliest deadline forever and starves everything else. `exit()` performs the same check in case the scan never observed the process while it was overdue.

Children inherit deadlines through `fork`, but `MAX_URGENT` is checked only in `setworkflow`. This gap is recorded in `LIMITATIONS.md`.

### 4.3 Priority donation through pipes

Donation is active only under policy 2.

**Holder definition.** The handout skeleton suggests a `pi->writer` pointer. That does not work for shell pipelines: the process running `a | b` in `sh.c` creates the pipe and forks both sides, so no process owns the write end, and a stored pointer would be empty at the first block or stale once a slot is reused. We define instead: a holder of pipe P is any live process with an open `struct file` of type `FD_PIPE` whose `pipe` is P and which is `writable`. Finding holders means scanning `NPROC x NOFILE` = 1024 slots, which is cheap at this scale. The definition over-approximates, because a process that merely holds the write end receives the donation even if it never writes. For that reason every test and workload program closes the pipe ends it does not use.

**Hooks.**

- `piperead`: when the pipe is empty and still has a writer, call `pipe_wait_begin(pi)` immediately before `sleep()` and `pipe_wait_end()` immediately after it returns, on every loop iteration and before the `killed` check. The pipe lock stays held across `pipe_wait_begin`, so no wakeup can be lost. No other change is made to `pipe.c`.
- `pipe_wait_begin` takes `ptable.lock`, sets `waiting_pipe`, and runs the donation walk if the reader has a finite effective deadline.
- `pipe_wait_end` takes `ptable.lock`, clears `waiting_pipe`, and runs the recompute.
- `exit()`, once it holds `ptable.lock` and files are closed: clear `waiting_pipe`, leave the workflow, run the recompute.
- `kill()` only marks the process. A killed donor's donation disappears when the donor wakes and exits.

**Donation walk.** An iterative depth-first search with an explicit stack of at most `NPROC` entries and a colour per process slot (white for unseen, gray for on the current path, black for finished). Starting from reader `q` with `dl = effective(q)`, for each holder `h != q` of `q->waiting_pipe`: if `dl_before(dl, h->donated)`, set `h->donated = dl` and record a `DONATE` event. If `h` is itself waiting on a pipe, continue from `h` with the same `dl`. Reaching a gray process is a cycle: record a `CYCLE` event, increment the counter, and do not follow the edge. Reaching a black process is just a second path to the same process and is skipped. Depth is also capped at `NPROC` as a second safeguard.

**Withdrawal.** Removing a single donation incrementally is error-prone when two readers have donated to the same writer. We recompute from scratch instead. Pass 1 sets `donated = NO_DEADLINE` for every live process. Pass 2 repeats, for at most `NPROC + 1` rounds and until nothing changes: for every process `q` with `waiting_pipe` set and a finite `effective(q)`, each holder `h` of that pipe takes the more urgent of `h->donated` and `effective(q)`. Donated values only ever move toward more urgent values within a finite set, so the loop terminates on cycles as well, and a second donor is restored correctly when the first leaves. The cost is `O(rounds x NPROC x NOFILE)`, which is irrelevant at `NPROC = 64`. The report justifies the choice on simplicity and ease of proof.

**Testing support.** `procinfo(pid, &st)` returns a process's state, own deadline, donated deadline and waiting flag so that tests can assert withdrawal. `tracectl` toggles debug printing of donation events in the form `donate: donor=<pid> recv=<pid> dl=<hex>` and `donate: cycle`.

Implementation note: `proc.c` needs `fs.h`, `sleeplock.h` and `file.h` (in that order, after `spinlock.h`) before it can read `struct file` fields.

### 4.4 Locking

The existing code already imposes this order:

| Order | Imposed by |
|---|---|
| `tickslock` then `ptable.lock` | The clock interrupt calls `wakeup` |
| `cons.lock` then `ptable.lock` | The console interrupt calls `wakeup` |
| `pipe->lock` then `ptable.lock` | `sleep()` inside pipe code |

Three rules follow, and they apply to every line of new code:

1. Nothing takes `tickslock`, `cons.lock` or a pipe lock while holding `ptable.lock`.
2. Nothing calls `cprintf` while holding `ptable.lock`. Events are written to the trace ring or to a small local array and printed after release. Holding `pipe->lock` while printing is fine.
3. The donation entry points are called with `pipe->lock` held and take `ptable.lock` internally, which matches the existing order.

Reading another process's `ofile[]` under `ptable.lock` is not synchronised by xv6. A stale read can cause a momentary over-donation or under-donation, and the next recompute corrects it. This is recorded in `LIMITATIONS.md` as a benign race.

### 4.5 Syscall interface

| No. | Call | Behaviour | Stage |
|---|---|---|---|
| 22 | `int hello(void)` | Prints `hello from kernel`, returns 0 (course exercise) | 1 |
| 23 | `int setsched(int policy)` | 0 `rr`, 1 `edf`, 2 `edf_donate`. Anything else returns -1. | 2 |
| 24 | `int setworkflow(int wid, int deadline_ticks)` | Joins or creates a workflow, subject to admission control (Section 4.2) | 2, 4 |
| 25 | `int schedinfo(struct sched_stats *dst)` | Fills the statistics struct | 2 |
| 26 | `int schedtrace(struct trace_ent *dst, int max)` | Copies trace entries oldest-first per CPU, returns the count | 6 |
| 27 | `int tracectl(int cmd)` | 0 trace off, 1 trace on, 2 clear, 3 donation debug on, 4 donation debug off | 5 (debug), 6 (rest) |
| 28 | `int procinfo(int pid, struct procstat *dst)` | Returns -1 if the pid is not found | 5 |

Structures shared between kernel and user live in `sched_api.h`, which has no kernel-only includes:

```c
struct sched_stats { int policy; int ncpu; uint ticks; int misses;
                     int donations; int cycles; int rejected; };
struct procstat    { int state; uint deadline; uint donated; int waiting; };
struct trace_ent   { uint tlo, thi; short cpu, pid, ev; int arg; uint seq; };
```

Team parameters are defined only in `sched_params.h` (kernel and user) and mirrored in `host/config.json` (host). They are never hard-coded elsewhere. The values below are placeholders until the instructor issues ours:

| Parameter | Placeholder |
|---|---|
| `NO_DEADLINE` | `0xffffffff` |
| `MIN_SLACK` | 20 ticks |
| `MAX_URGENT` | 8 |
| `NWF` | 8 |
| `TRACE_SIZE` | 256 |
| `MAX_HOGS` | 8 |

`host/config.json` additionally holds `xv6_dir`, `qemu_bin` (null by default), `cpus_allowed` (`[1, 3]`), the file `allowlist` (`/report.txt`, `/inbox.txt`, `/README`), `clamp` (false) and `W_ticks` (set after calibration).

### 4.6 Trace ring

Each CPU has a ring of `TRACE_SIZE` entries. Events are `SWITCH_IN`, `SWITCH_OUT`, `DONATE`, `WITHDRAW`, `CYCLE` and `DEADLINE_MISS`. Every writer already holds `ptable.lock`, so the ring needs no lock of its own, and it lives in `proc.c` for the same reason as the rest of the table-scanning code. Timestamps come from `rdtsc` (`asm volatile("rdtsc" : "=A"(x))`). We check in QEMU that the counter is monotonic, and if it is not we order by the global `seq` counter instead. The ring overwrites its oldest entries when full. The Stage 5 event array is replaced by the ring in Stage 6, keeping the deferred-print debug mode.

### 4.7 Guest programs

| Program | Purpose |
|---|---|
| `xrun <nonce> cmd args...` | Forks, execs `cmd`, waits, then prints `@@DONE <nonce>`. Prints `@@EXECFAIL <nonce>` if `exec` fails. |
| `wfgen <stages> <work> <bytes> <deadline> <hogs>` | Pipeline workload generator (Section 4.9) |
| `schedctl rr\|edf\|edf_donate` | Sets the policy |
| `schedstat` | Prints `struct sched_stats` |
| `schedtrace` | Prints trace entries as `tlo thi cpu pid ev arg seq` |
| `calib` | Runs the busy loop for N iterations and prints the tick delta |
| `ticktest` | Measures the tick rate with `sleep(500)` |
| `hello_test`, `edftest`, `donatetest`, `donate5`, `cycletest`, `killtest` | Tests (Section 5) |

### 4.8 Host agent

**Bridge.** `QemuBridge.start(cpus)` spawns `make qemu-nox CPUS=<n>` with `pexpect` (adding `QEMU=` and `QEMUEXTRA=-snapshot` when the config says so), then waits for `init: starting sh` and the `$ ` prompt. Every byte seen goes to `logs/<timestamp>.raw`. This `make` invocation is the only thing the bridge ever runs on the host.

`run(argv)` generates a random nonce, sends `xrun <nonce> <argv...>`, asserts the line is under 90 characters, and verifies that the console echo matches what was sent (retrying with a small per-character delay if characters were dropped). It then expects one of `@@DONE <nonce>`, `@@EXECFAIL <nonce>`, `panic:`, `--kill proc` or a timeout, and after `@@DONE` waits for the next prompt to resynchronise. The typed command never contains the string `@@DONE`, so the echo cannot fake completion. The result is an `Observation(status, output, elapsed)`. A kernel panic freezes xv6 silently, so the timeout is how a hung guest is detected. On a panic or timeout the bridge saves the log, restarts QEMU and reports the failure status. `restart(cpus)` accepts only 1 or 3.

**Tools and validator.**

| Tool | Guest command (fixed template) | Constraints |
|---|---|---|
| `list_files()` | `ls` | none |
| `read_file(path)` | `cat <path>` | Matches `^/?[A-Za-z0-9._]{1,14}$` (xv6 names are at most 14 characters) and is in the allowlist |
| `set_policy(p)` | `schedctl <p>` | One of `rr`, `edf`, `edf_donate` |
| `run_pipeline(stages, work, bytes, deadline, hogs)` | `wfgen ...` | Integers only. `2 <= stages <= 6`, `deadline >= MIN_SLACK`, `0 <= hogs <= MAX_HOGS`, `work` and `bytes` capped |
| `sched_stats()` | `schedstat` | none |
| `summarize(text)` | host only | No guest effect |

The validator rejects unknown tools, missing or extra arguments, wrong types (a Python `bool` is not accepted as an `int`) and out-of-range values before anything reaches the bridge. Rejection is the default. Clamping is available through `config.clamp`, in which case both the proposed and the clamped call are logged. The security rules for host code are fixed: no `eval`, `os.system` or `shell=True` on model text, and no API keys in the repository.

**Planners.** `DeterministicPlanner` is rule-based and is built first. Its `injected` mode proposes `run_pipeline(deadline=1, hogs=8)` after `/inbox.txt` has been read. `AdaptivePlanner` (Stage 7) runs a pilot under `rr` with the user's deadline, switches to `edf_donate` and reruns if the pilot missed, compares the two, and stops after at most three steps. Its decision rule is ordinary code over parsed observation fields. `OllamaPlanner` talks to `localhost:11434/api/chat` with a JSON schema so that the model returns a tool call and not shell text. It is optional and first in the cut order.

**Loop and audit.** `host/agent.py "<request>" [--planner ...] [--mode ...]` runs plan, validate, execute, observe for at most 8 steps. Each step appends one JSON object to `logs/audit.jsonl` with `ts`, `user_request`, `proposed_call`, `validated_call`, `validation_error`, `guest_output`, `observation_status`, `kernel_log_lines` (console lines beginning `donate:`, `admit:` or `sched:`) and `final_state`. These are the evidence fields the handout lists.

### 4.9 Workload and measurement

**`wfgen`.** The parent creates `stages - 1` pipes, forks the hogs first (busy loops with no workflow), records `t_start = uptime()`, then forks the stages. Stage 1 writes `bytes` in 64-byte chunks with `work` busy-loop units between writes. Middle stages read a chunk, burn `work`, and write it on. The last stage calls `setworkflow(1, deadline)` before anything else, reads to EOF burning `work` per chunk, and prints one line in a single `write()`:

```
RESULT policy=%d cpus=%d finish=%d deadline=%d miss=%d
```

Here `finish` is `uptime() - t_start` and `miss` is `finish > deadline`. The kernel's own miss counter from `schedstat` serves as a cross-check. If `setworkflow` fails, the program prints `wfgen: workflow rejected by kernel` and exits. Every stage closes the pipe ends it does not use. The parent closes all of its copies after forking, waits for the stage pids, then kills and reaps the hogs.

Two properties decide whether the experiment measures anything:

- Only the last stage carries the deadline. If every stage had it, EDF alone would already succeed and donation would have nothing to show.
- Stages must actually block and hogs must outnumber CPUs. This means `bytes >= 4 x PIPESIZE` (512) and `hogs >= cpus + 1`.

**Calibration.** `calib` is used to choose `work` so that one unloaded pipeline run takes a known `W` ticks (target 40 to 60). `W` is the mean of five unloaded runs on `CPUS=1` and is recorded with its spread in `PARAMS.md` and `config.json`.

**Experiment model.** With `h` hogs under fair sharing, the active stage gets about `1/(h+1)` of a CPU, so `T_RR ≈ (h+1)·W` on one CPU. With EDF and donation, `T ≈ W` plus overhead. The informative deadline window is therefore `W < D < (h+1)·W`. We set `D = round(α·W)` and sweep `α` over 1.2, 1.5, 2 and 3.

**Harness.** `harness/run_all.py` iterates over policy (`rr`, `edf`, `edf_donate`) x CPUS (1, 3) x 20 runs. For each run it restarts QEMU with `-snapshot`, sets the policy, runs the pipeline, parses the `RESULT` line with a strict regex, appends a CSV row and saves the raw log. CSV columns are `policy, cpus, run, alpha, finish, deadline, miss, status, commit_hash, rawlog_path`. The harness resumes after a crash by skipping finished rows, records `timeout` and `panic` rows without aborting, and supports `--dry-run` (2 runs per cell). The kernel is not rebuilt between runs of the same batch.

**Analysis.** `harness/analyze.py` excludes rows whose status is not `ok` and reports how many were excluded per cell. For each cell it reports n, misses, miss rate with a 95% bootstrap confidence interval (10,000 resamples, fixed seed), and mean and median finish time. It runs Fisher's exact test for `edf` against `edf_donate` at each CPU count. With n = 20 the test has little power, and QEMU's TCG timing is nondeterministic. Both caveats are stated wherever the numbers appear. Outputs are `results/summary.csv`, `results/summary.md` and three plots: `misses_bar.png`, `miss_vs_alpha.png` and `finish_box.png`. `host/plots/plot_gantt.py` draws one lane per CPU from `schedtrace` output, with markers for donation events.

---

## 5. Schedule

| Stage | Days | Deliverable | Exit criterion |
|---|---|---|---|
| 0 | 1-3 | Reading notes, repository, parameters, documentation scaffolding | `check_submission.sh 0` passes and the zip builds |
| 1 | 3-4 | `hello` syscall, bridge ping, larger disk, measured tick rate | `check_submission.sh 1` |
| 2 | 4-7 | Policy switch and baseline EDF, no donation | `check_submission.sh 2` |
| 3 | 4-8 (parallel) | Host agent: bridge, validator, deterministic planner, audit log | `check_submission.sh 3`, `audit.jsonl` exists |
| 4 | 8-10 | Integration, admission control, firm deadlines, injection demo | `check_submission.sh 4` and the Day-10 checkpoint |
| 5 | 11-13 | Priority donation | `check_submission.sh 5` and a real GDB session saved |
| 6 | 13-14 | Full `wfgen`, trace ring, unattended harness | `check_submission.sh 6` |
| 7 | 15-17 | Measurements, analysis, adaptive planner | `check_submission.sh 7`, `results.csv` exists |
| 8 | 18-20 | Freeze, rehearsal, packaging | `check_submission.sh 8`, tag `final` |

Every stage ends with a commit whose message follows one convention: `stageN: <summary>`, then a line for the main design decision, a line for what failed and why, and a line for test status. The stage's documentation updates (Section 6) are part of the same commit. Each test below becomes a row in `docs/TEST_TABLE.md` on the day it is designed.

EDF and donation are deliberately in separate stages. Debugging both at once is the most common way this project goes wrong.

### Stage 0 (Days 1-3): reading and scaffolding

**Goal.** Understand how xv6 picks the next process, how a process sleeps and wakes, and how a pipe blocks. Set up the repository and submission scaffolding so that nothing has to be assembled at the end. No kernel logic changes in this stage.

**Work.**

- Read `proc.c` (`allocproc`, `scheduler`, `sched`, `yield`, `forkret`, `sleep`, `wakeup1`, `wakeup`, `kill`, `fork`, `exit`, `wait`), `proc.h`, `pipe.c`, `trap.c` (the timer case and the `yield()` at the end), `syscall.c`, `sysproc.c`, `usys.S`, `spinlock.c`, `file.h`, `file.c`, `param.h`, `lapic.c`, `console.c`, `sh.c` (`runcmd`, the `PIPE` case, `buf[100]`) and the `Makefile`.
- Each member writes answers to the following in `docs/DESIGN.md` under "Reading notes", in their own words, with file and line references:
  1. How does `scheduler()` loop, and which lock does it hold across `swtch`?
  2. What do `sleep(chan, lk)` and `wakeup(chan)` do, and why must the caller hold `lk`?
  3. Where do `piperead` and `pipewrite` block, and who wakes them?
  4. How often does the timer fire, and why does only CPU 0 increment `ticks`?
  5. In `sh.c`, which process creates the pipe for `a | b`, and which processes inherit its ends?
- Follow the setup document: build QEMU, unpack the tarball, `make clean && make`, `make qemu-nox`. Confirm that `ls` works and `usertests` passes.
- Capture the baseline with `script -q logs/baseline_usertests.raw -c "make qemu-nox"`.
- Create the repository with a `.gitignore` for build outputs (`*.o *.d *.asm *.sym *.img _* kernel bootblock entryother initcode initcode.out mkfs vectors.S kernelmemfs dist/`), commit, and `git tag baseline`. Everything later is a diff against this tag.
- Create `sched_params.h`, `host/config.json` and `host/config.py` with the placeholders from Section 4.5.
- Create the documents listed in Section 6 with headers and empty tables, and the two scripts `tools/check_submission.sh` and `tools/make_zip.sh`.
- Obtain the team parameters from the instructor. We do not invent them.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-00a | `usertests` on the untouched tree | `ALL TESTS PASSED` (evidence: `logs/baseline_usertests.raw`) |
| T-00b | `tools/check_submission.sh 0` | Passes |
| T-00c | `python -c "import host.config"` | Loads without error |

### Stage 1 (Days 3-4): toolchain proof

**Goal.** Prove the whole toolchain end to end with the smallest possible change, and fix two things that would cause trouble later: the disk is too small, and we do not yet know the real tick rate.

**Work.**

- Add `hello()` as syscall 22, following the setup document: `syscall.h`, `user.h`, `usys.S`, `syscall.c`, `sysproc.c`, plus `hello_test.c` in `UPROGS` and `EXTRA`. Every member makes these six edits by hand once, since the viva asks which files a syscall touches.
- Raise `FSSIZE` to 4000 in `param.h` and rebuild with `make clean`.
- Write `ticktest.c` (`uptime()`, `sleep(500)`, `uptime()`), time it against a stopwatch, and record ticks per second in `PARAMS.md`. We do not assume 100 Hz. All later deadlines are in ticks.
- Write `host/bridge/qemu_bridge.py` with `start`, `run_raw(cmd, timeout=15)` and `close` (Ctrl-A then x, with a forced terminate as fallback), and `host/ping.py`, which boots, runs `ls`, prints the result and exits. The console echoes input and ends lines with `\r\n`, and a single read is never assumed to return a whole response.
- Fix the exact QEMU launch line (`QEMU=` path, `QEMUEXTRA=-snapshot`, after checking that the Makefile honours `QEMUEXTRA`) and document the bridge method in `docs/bridge.md`, as the agent guide requires.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-01 | `hello_test` in xv6 | Prints `hello from kernel`, then `hello() returned 0` |
| T-02 | `python host/ping.py` | Prints the `ls` listing, including `README` and `hello_test` |
| T-03 | `ticktest` | Tick difference of about 500. Ticks per second computed from the stopwatch. |
| T-04 | `usertests` after the `FSSIZE` change | `ALL TESTS PASSED` |
| T-05 (negative) | Temporarily remove the `UPROGS` entry | `hello_test` is not found. Restore afterwards. |

### Stage 2 (Days 4-7): policy switch and baseline EDF

**Goal.** Give every process a deadline and make the scheduler pick the runnable process with the nearest one, with a runtime switch between `rr`, `edf` and `edf_donate`. Donation is not implemented yet, so policy 2 behaves like policy 1 for now.

**Work.**

- Implement Section 4.1 and the workflow table from Section 4.2, with admission control as a stub that accepts everything.
- Add syscalls 23 to 25 and `sched_api.h`.
- Write `schedctl`, `schedstat` and `edftest`. In `edftest` a parent forks two children that each burn about 5 seconds of CPU. Child A calls `setworkflow(1, 100)` and child B calls `setworkflow(2, 200)`. Each prints a completion line with a single `write()`.
- Agree the deadline unit semantics (relative ticks at the call, absolute ticks stored) and write them in `DESIGN.md`.
- `pipe.c` is not touched in this stage.

**Manual verification.**

- Review the `scheduler()` diff line by line against Section 4.4. In particular, an idle CPU must still release `ptable.lock` and loop back through `sti()`.
- Save the `edftest` output under both `rr` and `edf` to `logs/`.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-06 | `schedctl edf; edftest`, `CPUS=1` | The deadline-100 child finishes first |
| T-07 | `schedctl rr; edftest`, `CPUS=1` | Both finish close together |
| T-08 | `schedctl edf; usertests` | `ALL TESTS PASSED` (also exercises the tie-break) |
| T-09 | `schedctl rr; usertests` | `ALL TESTS PASSED` |
| T-10 | `schedctl edf_donate; usertests` | `ALL TESTS PASSED` |
| T-11 (negative) | `setsched(7)` | Returns -1 |
| T-12 (negative) | `setworkflow(1, 0)`, and a second `setworkflow` call by the same process | Both return -1 |
| T-13 | Boot with `CPUS=3` | No panic |

### Stage 3 (Days 4-8, in parallel with Stage 2): host agent

**Goal.** A working agent loop against the stock scheduler: the planner proposes a tool call, the validator checks it, the bridge executes a fixed template, and every step is logged.

**Work.**

- Guest: `xrun.c`, and a stub `wfgen.c` that will be replaced in Stage 4.
- Host: extend the bridge with `run(argv)`, then add `tools.py`, `validator.py`, `planners/` (base, deterministic, Ollama), `audit.py`, `loop.py` and `agent.py`, all as specified in Section 4.8.
- Unit tests in `host/tests/test_validator.py` covering: unknown tool, missing argument, extra argument, `../x`, `/a/b`, a 20-character name, wrong type, `bool` passed as `int`, deadline below `MIN_SLACK`, `hogs=99`, and one valid call.
- Add `report.txt` and `inbox.txt` to the image by extending both the `fs.img` dependency line and the `./mkfs fs.img ...` command in the Makefile, then rebuild with `make clean`. We write the file contents ourselves. `report.txt` holds three harmless lines. `inbox.txt` holds one benign line and one injected instruction asking for a deadline-1 pipeline with 8 hogs.
- Fix the allowlist in `config.json`.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-14 | `python host/agent.py "list files then read /report.txt"` | Listing and file contents returned, audit lines written |
| T-15 (negative) | Planner proposes `rm_all` | Rejected before the bridge, no QEMU traffic |
| T-16 (negative) | `read_file("../etc/passwd")` | Rejected |
| T-17 (negative) | `read_file("/a/b")`, 20-character name | Rejected |
| T-18 (negative) | `read_file("/notinallowlist")` | Rejected |
| T-19 (negative) | `run_pipeline(deadline=1)` | Rejected by the validator |
| T-20 (negative) | `run_pipeline(hogs=99)` | Rejected |
| T-21 (negative) | Missing argument, extra argument, `True` as an integer | Rejected |
| T-22 | Forced timeout (a command that never prints `@@DONE`) | `status=timeout`, VM restarted, no success reported |
| T-23 | `xrun` of a missing program | `@@EXECFAIL`, reported as an error |
| T-24 | `pytest host/tests` | All pass |

### Stage 4 (Days 8-10): integration, admission control, injection demo

**Goal.** Join the two tracks so that the agent can set a policy, launch a small pipeline and get back a parsed result. Add the kernel-side gate, then stage the attack and show that both layers hold.

**Work.**

- Kernel: replace the admission stub and add firm deadlines (Section 4.2).
- Guest: a minimal real `wfgen` supporting 2 stages (other stage counts print `unsupported` until Stage 6), with the `RESULT` line and the rejection message from Section 4.9.
- Host: `host/demos/injection_demo.py` with three parts: a benign run (`set_policy edf`, then `run_pipeline` with deadline 300, `RESULT` parsed into the observation), the injected run (validator blocks it, proposed and validated calls both logged), and a helper that prints the exact line to type at the xv6 prompt and afterwards checks the raw log for `admit: rejected`.
- Decide between rejecting and clamping in the validator and record the decision in `DESIGN.md`. Rejecting is the cleaner option.
- Confirm that `MIN_SLACK` agrees between `sched_params.h` and `config.json`.

**Manual verification.**

- Run the injection demo live at least once, watching the console.
- Perform the shell bypass by hand. It is the point of the exercise and is not delegated to any script or agent.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-25 | Agent: `set_policy edf`, then `run_pipeline` (2 stages, deadline 300), `CPUS=1` | `RESULT` line with finish, deadline and miss |
| T-26 (negative) | Injected agent run | Validator blocks it, no hogs started |
| T-27 (negative) | Manual: `wfgen 2 200 4096 1 8` at the xv6 prompt | `wfgen: workflow rejected by kernel`, and the kernel prints `admit: rejected ... reason=slack` |
| T-28 (benign control) | Manual: the same command with a legitimate deadline | Accepted, `RESULT` printed |
| T-29 (negative) | More than `MAX_URGENT` urgent processes | The extra ones are rejected with `reason=urgent` |
| T-30 | Overdue process | Counted as one miss, then scheduled as best-effort |
| T-31 | `usertests` under `rr`, `edf`, `edf_donate` | All pass |
| T-32 | Pipeline run on `CPUS=3` | No panic |
| T-33 | Day-10 checklist | Every item passes, or the cut is documented |

**Day-10 checkpoint.** All four must hold: the agent runs end to end, EDF works on `CPUS=1` in the happy path, admission control rejects a deadline of 1, and `usertests` passes. The checklist is filled in honestly in `JOURNAL.md`. If any item fails, scope is cut that day according to Section 1.2 and the cut is written down with its reason.

### Stage 5 (Days 11-13): priority donation

**Goal.** Implement Section 4.3. This is the technically deepest part of the project and the one the hidden tests target.

**Work.**

- Before writing code, draw the 4-stage pipeline on paper: which process sleeps on which pipe, who holds each write end, and where donation flows. Every member must be able to redraw it at the viva. The drawing goes into the report.
- Implement `holds_write_end`, `pipe_wait_begin`, `pipe_wait_end`, the donation walk, `recompute_donations_locked`, the `exit()` hook, `procinfo` (28) and the debug half of `tracectl` (27).
- Test programs, each with strict fd hygiene:
  - `donatetest`: a 4-stage chain where stage 1 writes more than 512 bytes in chunks, stages 2 and 3 forward, and stage 4 calls `setworkflow(1, D)` first and reads to EOF. One hog with no workflow. Prints one `RESULT` line.
  - `donate5`: the same with 5 stages and one hog.
  - `cycletest`: two processes each read the pipe the other writes. They deadlock by design, so the parent sleeps and then kills both.
  - `killtest`: a donor is killed while its donation is active, plus a two-donor variant in which one donor is killed.

**Manual verification.**

- Run the 4-stage test under `edf` first and save the log of it failing, then run it under `edf_donate`.
- Review every exit path of `piperead`, `pipe_wait_begin`, `pipe_wait_end` and `exit()` for an unreleased lock or a stale `waiting_pipe`. Early returns are the usual culprit.
- Verify the lock order by reading the code and listing every acquisition site. No path may take `pipe->lock`, `cons.lock` or `tickslock` while holding `ptable.lock`.
- When something hangs, debug it in GDB and save the session to `docs/gdb/`. Useful commands: `b scheduler`, `bt`, `p ptable.proc[3]`, `info threads` (each CPU is a thread). The rubric asks for one real bug found and fixed, and the session we submit will be a real one.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-34 | 4-stage chain with 1 hog, `edf`, `CPUS=1` | Last stage misses |
| T-35 | Same under `edf_donate` | Meets the deadline. Debug lines show the chain from stage 3 to 2 to 1. |
| T-36 | 5-stage chain with an unrelated hog (hidden-test category) | Same improvement |
| T-37 | Two readers donate to one writer, one reader finishes | Remaining donation preserved (`procinfo`) |
| T-38 | Pipe cycle between two processes (hidden-test category) | Exactly one `donate: cycle`, no hang |
| T-39 | Donor killed while its donation is active (hidden-test category) | Receiver's `donated` returns to `NO_DEADLINE` |
| T-40 | Two donors, one killed | The other donation remains |
| T-41 | `usertests` under `edf_donate` | All pass |
| T-42 | `donatetest` on `CPUS=3` | No panic, no deadlock |
| T-43 (negative) | Policy `rr` or `edf` | `donate:` lines never appear |
| T-44 | Pipeline with `bytes < 512` | No blocking and no donation (sanity check) |
| T-45 | Stress: 20 consecutive runs | No hang, no panic |

### Stage 6 (Days 13-14): workload generator, trace ring, harness

**Goal.** Build the measurement apparatus: a configurable workload, a kernel trace that can be drawn as a timeline, and a harness that runs the whole experiment matrix unattended.

**Work.**

- Kernel: `rdtsc()` in `x86.h`, the trace ring (Section 4.6), syscall 26, and the remaining `tracectl` commands.
- Guest: full `wfgen` for 2 to 6 stages, `calib`, `schedtrace`.
- Host: `host/plots/plot_gantt.py` and `harness/run_all.py` (Section 4.9).
- Calibrate `work` and record `W`. Choose hog counts: 2 or 3 for `CPUS=1`, 4 or 5 for `CPUS=3`.
- Run the harness with `--dry-run` before any full batch, and note the commit hash used.
- Inspect one Gantt chart by eye. If the donation markers do not line up with the chain, the trace has a bug.
- Donation logic is not changed in this stage.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-46 | `wfgen` unloaded | `miss=0`, finish about `W` |
| T-47 | `wfgen` with hogs under `rr`, tight deadline | Likely `miss=1` |
| T-48 | Pipes block | Trace shows readers sleeping. `DONATE` events appear under `edf_donate`. |
| T-49 | Trace ring wraps | No crash after many events |
| T-50 | Harness `--dry-run` | CSV rows for all 6 cells |
| T-51 (negative) | Kill QEMU mid-run | Harness records the failure row and continues |
| T-52 | Rerun the harness | Skips finished rows |
| T-53 | Interleaving check | `RESULT` lines are never corrupted under the strict parser |

### Stage 7 (Days 15-17): measurements and the adaptive planner

**Goal.** Produce the results and the graphs, and show the agent using its own observations to choose a policy. No kernel changes.

**Work.**

- Write `docs/predictions.md` and commit it before the full batch runs. The expected picture: `rr` shares the CPU with the hogs and misses. `edf` also misses, because the urgent last stage is asleep while stages 1 to 3 have no deadline. `edf_donate` misses far less. Committing the prediction first is what lets us tell a real result from a bug.
- Run the full batch: 3 policies x 2 CPU counts x 20 runs at the main α, then the sweep. Ten runs per cell is acceptable for the sweep if time is short, and the report will say so.
- Write `harness/analyze.py`, `host/plots/plot_results.py`, `host/planners/adaptive.py` (with `--planner adaptive` in `agent.py`) and `tools/index_evidence.py`, which maps every graph to the CSV rows and raw logs behind it.
- Inspect every odd run, such as a miss under donation or a panic. Outliers are not deleted. They are logged in `LIMITATIONS.md`.
- If the results contradict the prediction, debug before plotting. The usual causes are pipes that never block, hogs not outnumbering CPUs, a deadline outside `(W, (h+1)·W)`, or a tie-break that is not applied.
- Choose the three graphs that fit in the report. Keep every raw log.

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-54 | Misses, 4-stage, `CPUS=1` | `rr` high, `edf` high, `edf_donate` clearly lower |
| T-55 | `CPUS=3` | The pattern holds or is weaker, with a written explanation |
| T-56 | Miss rate against α | `edf_donate` reaches near zero at a smaller α |
| T-57 | Gantt chart for `edf` | Stages 1 to 3 starved while the hog runs |
| T-58 | Gantt chart for `edf_donate` | Stages 1 to 3 run early, with donation markers just before |
| T-59 | Adaptive agent with a tight deadline | Switches to `edf_donate` after a miss. The audit log shows both runs. |
| T-60 | Every graph has a registered raw-log source | `EVIDENCE_INDEX.md` is complete |

### Stage 8 (Days 18-20): freeze, rehearse, package

**Goal.** No new features. Read through the documents, fill the last gaps, rehearse the viva, and produce the submission.

**Work.**

- Tag the final commit (`git tag final`). After that, kernel code changes only for bug fixes.
- Clean-room rerun from a fresh clone: `make clean && make`, `make qemu-nox`, `usertests`, agent demo, injection demo including the manual shell bypass. Anything that depends on local state is a bug.
- Extend `check_submission.sh 8` to fail on placeholders anywhere in `docs/`, on evidence rows pointing at missing files, on missing per-person entries in `CONTRIBUTIONS.md`, and on build outputs inside the zip.
- Complete `VIVA.md`: a one-page summary in which every statement cites a file and function, plus the drills below. Each drill lists the files to touch and a three-line approach, and is rehearsed once against a timer (target under 10 minutes).
  - Donation through `wait()` (the child is the holder)
  - FIFO tie-break
  - Moving the cycle check earlier or later
  - A new counter in `sched_stats`
  - Changing `MIN_SLACK` and showing a rejection
  - Capping donation depth at K
  - A new trace event
  - Validator clamps in place of rejecting
- Cross-check `TEST_TABLE.md` against the test code in `host/tests` and the guest test programs, in both directions.
- Hand-copy the report from `REPORT_NOTES.md`. It is strictly two pages and includes the donation-chain diagram, the best graphs, `effective(p)`, the wrap-safe comparison, `T_RR ≈ (h+1)·W`, the recompute termination argument and the cycle bound.
- Ask the instructor whether raw logs and graphs belong inside the zip or in a separate evidence bundle (Section 9).

**Tests.**

| ID | Test | Expected |
|---|---|---|
| T-61 | Clean clone, full build and demos | Works from scratch |
| T-62 | Injection demo end to end | Validator blocks, shell bypass is blocked by the kernel, benign control passes |
| T-63 | `usertests` under all three policies | Pass |
| T-64 | Zip contents | Only added or modified files, per-person highlights present |
| T-65 | Timed viva drills | Each completed |

---

## 6. Documentation and evidence

Nothing is written at the end. The submission documents exist from Stage 0, each stage appends to them, and `tools/check_submission.sh <stage>` verifies that we are on track. By Stage 8 the remaining work is a read-through.

### 6.1 Repository layout

```
repo/
├── xv6-public/           course tree plus our changes
│   ├── sched_params.h    team parameters (kernel and user)
│   └── sched_api.h       structs shared by kernel and user
├── host/                 bridge/, planners/, validator.py, tools.py, audit.py,
│                         loop.py, agent.py, config.json, tests/, demos/, plots/
├── harness/              run_all.py, analyze.py
├── docs/                 see 6.2
├── logs/                 raw QEMU transcripts, audit.jsonl
├── results/              CSVs, graphs, Gantt charts
└── tools/                make_zip.sh, check_submission.sh, index_evidence.py
```

### 6.2 Documents and when they are updated

| File | Content | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
|---|---|---|---|---|---|---|---|---|---|---|
| `JOURNAL.md` | One entry per stage: done, failed, why | x | x | x | x | x | x | x | x | x |
| `DESIGN.md` | Data structures, algorithms, lock order, decisions | x | x | x | x | x | x | x | | read |
| `PARAMS.md` | Parameters, values, source, where defined | x | x | | | | | x | x | |
| `SYSCALLS.md` | Syscall number registry | | x | x | | | x | x | | |
| `TEST_TABLE.md` | Every test: expected, observed, evidence path | | x | x | x | x | x | x | x | audit |
| `EVIDENCE_INDEX.md` | Every graph and claim mapped to its raw log or CSV | x | x | x | x | x | x | x | x | verify |
| `LIMITATIONS.md` | Limits, recorded the day they are found | | | x | x | x | x | x | x | read |
| `REPORT_NOTES.md` | The two-page report in typed form | | | x | | x | x | | x | polish |
| `VIVA.md` | Summary sheet, questions, drills | | | x | x | x | x | x | x | drills |
| `CONTRIBUTIONS.md` | Who did which files, functions and tests | x | x | x | x | x | x | x | x | final |
| `bridge.md` | Bridge method, prompts, limits | | x | | x | | | | | |
| `predictions.md` | Written before the full measurement run | | | | | | | | x | |
| `gdb/` | Saved GDB sessions | | | | | | x | | | verify |

### 6.3 Rules

1. **Tests.** Every test is a row from the day it is designed, with columns `ID | Stage | Test | Input | Expected | Observed | Evidence file | Type` (positive, negative or benign control). Observed stays `UNRUN` until a person has run the test and captured the evidence. Observed results, numbers and log excerpts are never written from expectation.
2. **Evidence.** Every raw log is registered in `EVIDENCE_INDEX.md` the day it is created, with its path, the command that produced it and the commit hash.
3. **Limitations.** Each one is recorded the day it is found, phrased as what our model leaves out compared with a full implementation.
4. **Cadence.** At least every two days: commit, add a `JOURNAL.md` entry covering what failed and why, and run `check_submission.sh` for the current stage.
5. **Report.** `REPORT_NOTES.md` is kept within the report's word budget from the start: Model 120, Locking 100, Donation and proofs 150, Security 80, Results 150 plus graphs, Problems 80, Limits 60.

### 6.4 Packaging scripts

`tools/make_zip.sh` zips only files added or modified since the `baseline` tag (`git diff --name-only --diff-filter=AM baseline HEAD`, plus untracked new files), excludes build outputs, and writes `dist/KernelKraft_3.zip`. It runs as a dry run at the end of every stage so that packaging surprises show up early.

`tools/check_submission.sh <stage>` checks that every document due by that stage exists, is non-empty and has no unfilled placeholders, and that `TEST_TABLE.md` has no `UNRUN` rows for completed stages. It then calls `make_zip.sh` and prints the file list and size. Due stages: `JOURNAL`, `DESIGN`, `PARAMS`, `CONTRIBUTIONS`, `EVIDENCE_INDEX` (0), `SYSCALLS`, `TEST_TABLE` (1), `LIMITATIONS`, `REPORT_NOTES`, `VIVA` (2), `logs/audit.jsonl` (3), at least one file in `docs/gdb/` (5, as a warning until Stage 8), `results/results.csv` (7).

---

## 7. Team and working practices

The work divides into four workstreams. The team has three members, so the fourth is shared.

| Workstream | Scope | Owner |
|---|---|---|
| W1 Scheduler core | `proc.c`, `proc.h`, `setsched`, `setworkflow`, EDF, tie-break, admission control | |
| W2 Donation | `pipe.c` hooks, donate, withdraw and cycle logic, trace events | |
| W3 Host agent | Bridge, validator, planners, injection demo | |
| W4 Workload and evidence | `wfgen`, harness, experiments, graphs, report notes, GDB session, test table | Shared: `wfgen` and calibration with W1, harness and analysis with W3, GDB session and test table with W2 |

Practices:

- Everyone commits under their own Git identity and puts an `// Author:` line at the top of each file they create. `git shortlog -sn` is part of the contribution evidence.
- Changes are kept minimal, and every non-obvious design choice gets a short comment.
- The following are always done by a team member in person: the `hello` syscall edits, the tick measurement, the lock-order review, the manual shell bypass, and the GDB session.

---

## 8. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Starting donation before EDF is tested | Two interacting bugs that cannot be separated | Separate stages, and the Stage 2 exit criterion must pass first |
| Workload never blocks a reader, or hogs do not outnumber CPUs | No contention, so all policies look the same | `bytes >= 4 x PIPESIZE`, `hogs >= cpus + 1`, T-44 and T-48 |
| Every stage is given the deadline | EDF alone succeeds and donation shows nothing | Only the last stage calls `setworkflow` |
| `cprintf` while holding `ptable.lock` | Deadlock against the console interrupt | Deferred printing through the trace ring or a local array |
| `tickslock` taken under `ptable.lock` | Deadlock against the clock interrupt | `now_ticks()` unlocked read |
| Stale `waiting_pipe` after wake, kill or exit | Phantom donations | Cleared in `pipe_wait_end` and `exit()`, checked by T-39 and T-40 |
| Unclosed pipe ends in `wfgen` or the tests | Extra holders, no EOF, over-donation | fd hygiene rule, reviewed in every test program |
| Relying on the validator alone | The security claim is unproven | Manual shell-bypass test T-27 |
| Compiler warnings | Build fails under `-Werror` | Build after every change |
| Stale `fs.img` after changing `param.h` or the fs layout | Programs silently do not fit | `make clean` after those changes |
| Guest command line over 99 characters | Command truncated by the shell | Bridge asserts a length under 90 |
| Interleaved console output | `RESULT` parser breaks | Single-`write()` lines and a strict regex (T-53) |
| TCG timing noise with n = 20 | Weak statistical claims | Confidence intervals, stated caveats, α sweep |
| Documentation left to the end | Untested claims at submission | `check_submission.sh` gate at every stage |
| Fabricated GDB log or hidden limitation | Loses more marks than the honest version, and fails at the viva | Real session saved in Stage 5, `LIMITATIONS.md` kept current |
| Schedule slip in Part 1 | Donation squeezed | Day-10 checkpoint and the cut order in Section 1.2 |

---

## 9. Submission

**A. `KernelKraft_3.zip`** (naming rule `Team_Name_problem_no`), containing only files added or modified relative to the `baseline` tag:

| Group | Contents |
|---|---|
| Kernel | Modified `proc.c proc.h pipe.c defs.h syscall.c syscall.h sysproc.c usys.S user.h param.h x86.h Makefile`, and new `sched_params.h sched_api.h` |
| Guest programs | `xrun.c wfgen.c schedctl.c schedstat.c schedtrace.c edftest.c donatetest.c donate5.c cycletest.c killtest.c calib.c ticktest.c hello_test.c`, `report.txt`, `inbox.txt` |
| Host | `host/` and `harness/` |
| Documents | `docs/` |
| Per-person highlights | `docs/CONTRIBUTIONS.md` and the `// Author:` headers |

**B. Evidence.** `logs/` (raw per-run transcripts and `audit.jsonl`), `results/` (CSVs, graphs, Gantt charts) and `docs/gdb/`. Graphs must be accompanied by the raw QEMU logs that produced them. The zip rule says "only files added or modified for the implementation", so unless the instructor says otherwise this goes in a separate bundle, `KernelKraft_3_evidence.zip`.

**C. Report.** Handwritten, strictly two pages, copied from `docs/REPORT_NOTES.md`.

**D. Viva.** A laptop with the repository at tag `final`, QEMU built, the injection demo ready, and every member prepared for a live modification.

---

## 10. Rubric coverage

| Rubric item | Where it is satisfied |
|---|---|
| Per-team parameters | `sched_params.h` and `config.json`, never hard-coded (Stage 0, `PARAMS.md`) |
| Hidden tests (5-stage chain with a hog, pipe cycle, donor exits) | T-36, T-38, T-39, automated in the Stage 6 harness |
| Own run evidence | Raw logs per run, the GDB session from Stage 5, `EVIDENCE_INDEX.md` |
| Live viva change | `VIVA.md` drills, built up from Stage 2 and rehearsed in Stage 8 |
| Design journal with a note every two days | `JOURNAL.md` and the stage commit messages |
| Documented limits | `LIMITATIONS.md` |
| Agent guide: tools, bridge, structured calls, injection test, kernel refusal, test table, logs | Stages 3 and 4, `TEST_TABLE.md` with positive, negative and benign-control rows |
| Zip, per-person highlights, two-page handwritten report | Section 9 |
