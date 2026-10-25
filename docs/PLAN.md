# Project 3: Deadline Scheduler with Priority Donation, Agent-Driven and Injection-Resistant

CSL3030 Operating Systems Lab · IIT Jodhpur · **xv6-public (x86, 32-bit) running in QEMU**

> **Version note.** This replaces the earlier xv6-riscv plan. The course setup document uses the `cs236-xv6-linux.tgz` tree (xv6-public, i386), so every kernel detail below (syscall plumbing, locks, `sleep`, console, build commands) is rewritten for that tree. The architecture-independent ideas (EDF, donation, agent, validator, admission control) are unchanged.

**How each stage is written.** Every stage has the same blocks:

1. **In plain words**: what and why, no jargon.
2. **Technical details**: the real design, with every jargon term explained.
3. **Living documents to update**: the exact files you update *now*, so that nothing has to be compiled together at the end.
4. **Manual steps**: things only a human should do.
5. **Agent prompt**: paste into Copilot (after the master prompt in section 7).
6. **Test**: what to run; every test becomes a row in `docs/TEST_TABLE.md` immediately.
7. **Commit note**: ready-made message.
8. **Definition of done**: a command that must pass before you move on.

---

## 0. What changed from xv6-riscv to xv6-public (read this first)

| Topic | Old (riscv) assumption | Now (xv6-public, x86) |
|---|---|---|
| Kernel print | `printk()` | `cprintf()`. Supports only `%d %x %p %s %c %%` (no `%u`, no `%l`). Print unsigned values with `%x`. |
| Adding a syscall | `usys.pl`, `uint64 sys_x(void)` | `usys.S` (`SYSCALL(x)`), `int sys_x(void)`, number in `syscall.h` (next free is **22**, used by `hello`; yours start at 23). |
| Syscall arguments | registers `a0..a5` | pushed on the **user stack**; kernel reads them with `argint(n,&v)` (returns -1 on failure), `argptr(n,&p,size)`, `argstr(n,&s)`. |
| Copy to user | `copyout` | `argptr` validates the pointer range, then the kernel writes through it directly. Never skip `argptr`. |
| Sleeping | `sleep_prepare()` + `sleep()` | classic `sleep(chan, lk)` and `wakeup(chan)`. |
| Process locks | one lock per process | **one global `ptable.lock`** protects every process. No per-process lock exists. |
| Timestamps | `r_time()` | `rdtsc` CPU instruction (you add a tiny inline function to `x86.h`). |
| User programs | `printf("..")`, `exit(0)` | `printf(1, "..")` (fd first), `exit()` with **no status**, `wait()` with **no status** (returns pid). |
| Build/run | `make qemu` | `make qemu-nox CPUS=1` (add `QEMU=/path/qemu-system-i386` if you built QEMU yourself, as in the setup doc). |
| Debugging | gdb port 26000 | `make qemu-nox-gdb`, then `gdb -x .gdbinit kernel` (the port is printed in `.gdbinit`). |
| Compiler | lenient | `-Wall -Werror -m32`: **any warning breaks the build**. |
| Disk | roomy | `FSSIZE 1000` blocks (about 940 usable). Your new programs will not fit, so we raise it (Stage 1). |
| Clock | per-CPU | only **CPU 0** increments `ticks`. Lock order `tickslock -> ptable.lock` already exists. |
| Shell input | 128 | the xv6 shell reads at most **99 characters** per line (`char buf[100]` in `sh.c`). Keep guest commands under 90. |

---

## 1. The pitch

The handout asks for EDF plus donation through pipes. The agent guide asks for a host-side Python agent that drives xv6 through a QEMU bridge. Your project unifies them:

> **An LLM agent that plans and launches deadline-bound pipeline workflows on xv6, observes whether they met their deadlines, and adapts. The kernel, not the agent, guarantees fairness and refuses deadline abuse, even when the agent is prompt-injected.**

Three results to show at the viva:

1. **Kernel result:** EDF with transitive donation reduces deadline misses.
2. **Agent result:** closed-loop planning over a real guest OS.
3. **Security result:** an injected agent tries to grab the CPU with deadline 1; it fails at two layers (tool validator and kernel), and the kernel layer holds even if you type the command yourself at the xv6 shell.

### The whole idea in easy words

- Normal xv6 gives each ready program a turn in a circle (round-robin). It does not know some jobs have a "must finish by" time.
- **EDF (Earliest Deadline First)**: always run the ready job whose deadline is nearest.
- **Priority inversion (the problem):** in `A | B | C | D`, the last stage D is urgent but asleep, waiting for C, which waits for B, which waits for A. A, B, C have no deadline, so a CPU-hungry background program (a "hog") beats them and D misses its deadline.
- **Priority donation (the fix):** when D goes to sleep waiting on a pipe, it *lends* its urgency to whoever can fill that pipe (C), and C lends to B, B to A. The chain now outranks the hog.
- **Agent:** a Python program on your laptop types approved commands into xv6 and reads the results.
- **Security:** if text inside a file tricks the agent into launching a deadline-1 pipeline with 8 hogs, the validator blocks it, and even without the validator the kernel refuses. An agent can be fooled; the kernel cannot.

---

## 2. Architecture

```
HOST (Ubuntu)                                   GUEST (xv6-public i386 in QEMU)
┌────────────────────────────────────┐          ┌──────────────────────────────┐
│ Planner (rules -> Ollama/Llama)    │          │ user/: xrun, wfgen, schedctl,│
│        │ JSON tool call            │          │  schedstat, schedtrace, tests│
│ Validator (schema+range+policy)    │ serial   │            │ syscalls (int 64)│
│        │ validated action          │ console  │ kernel: EDF + donation +     │
│ Bridge (pexpect, sentinels, logs)──┼──────────┼─► admission control + trace  │
│        │ observation               │          └──────────────────────────────┘
│ Audit log (JSONL) + plots          │
└────────────────────────────────────┘
```

---

## 3. Novelties

| # | Novelty | Why it's impressive |
|---|---|---|
| N1 | **Runtime-switchable policy** (`rr`, `edf`, `edf_donate`) via `setsched()` | One kernel binary produces all three data sets. |
| N2 | **Pipe writer discovery by scanning fd tables**, not a single `pi->writer` pointer | A shell-built pipeline has no single writer pointer; the scan finds every process holding the write end. |
| N3 | **Fixpoint recompute on withdrawal** | Handles multiple donors, chains and cycles uniformly. |
| N4 | **Per-CPU trace ring** with `rdtsc` timestamps, `schedtrace`, Python Gantt chart | Visual proof that donation works. |
| N5 | **Admission control** and **firm deadlines** | Prevents deadline abuse and the EDF "domino effect". |
| N6 | **Agent closed loop**: pilot run, measure misses, pick policy/deadline, re-run | Real use of observations. |
| N7 | **Scheduler injection demo** | Reuses the course thesis "the kernel enforces". |
| N8 | **Slack sweep**: miss rate vs deadline slack α | Richer graph than required. |
| N9 *(stretch)* | Donation through `wait()` | Mechanism generalises beyond pipes. |
| N10 | **Deterministic runs** using QEMU `-snapshot` (disk resets every boot) | Reproducible measurements. |

---

## 4. Team split

- **P1, scheduler core:** `proc.c`, `proc.h`, `setsched`, `setworkflow`, EDF, tie-breaking.
- **P2, donation:** `pipe.c`, donate/withdraw/cycle logic, trace events.
- **P3, agent:** bridge, validator, planners, injection demo.
- **P4, workload and evidence:** `wfgen`, harness, experiments, graphs, report notes. A fifth person takes the GDB session and the test table.

Everyone commits under their own Git identity (`git shortlog -sn` is evidence of who did what) and puts `// Author: Pn` at the top of each file they create.

---

## 5. Glossary (jargon used in this plan)

| Term | Meaning |
|---|---|
| **Syscall / trap** | A user program asks the kernel to do something by executing `int 64`. The CPU switches to kernel mode and saves the user registers in a *trapframe*. |
| **Tick** | One timer interrupt. xv6 counts them in the global `ticks`; `uptime()` returns it. Time in this project is measured in ticks. |
| **Preemption** | The kernel forcibly takes the CPU from a running process. In xv6 each timer interrupt calls `yield()`, so the scheduler re-decides every tick. |
| **Runnable / running / sleeping** | Process states. Runnable = ready, waiting for a CPU. Sleeping = blocked until someone calls `wakeup` on its *channel* (an address used as a label). |
| **Context switch (`swtch`)** | Saves one set of CPU registers and loads another. The scheduler loop of each CPU switches into a process and the process switches back. |
| **`ptable.lock`** | The single spinlock guarding the process table. Held while scheduling. |
| **Spinlock** | A lock that busy-waits. While held, interrupts are off on that CPU. Never sleep while holding one (except through `sleep()`, which releases it correctly). |
| **Deadlock** | Two CPUs each hold a lock the other wants. Prevented by always taking locks in one global order. |
| **Lock order** | The rule "if you need A and B, always take A first". Our order is in `docs/DESIGN.md`. |
| **EDF** | Earliest Deadline First scheduling. |
| **Priority inversion** | A high-priority job is blocked by a low-priority one that the scheduler ignores. |
| **Priority donation** | The blocked job lends its priority to the one blocking it. *Transitive* = passed along a chain. |
| **Cycle** | A waits on B and B waits on A. Donation walks must not loop forever on it. |
| **Fixpoint** | Repeating an update until nothing changes. Our recompute terminates because values only decrease. |
| **Wraparound** | `ticks` is a 32-bit unsigned that eventually goes from `0xffffffff` back to 0. Compare times by subtracting and checking the sign, never with plain `<`. |
| **Tie-break** | Rule for choosing between equal deadlines. Without a fair one, one process can starve. |
| **Starvation** | A runnable process never gets the CPU. |
| **Admission control** | The kernel refuses new real-time requests that would be unreasonable (too tight, too many). |
| **Firm deadline** | A deadline that is dropped (job reverts to normal) once missed, so one late job cannot hog the CPU forever. |
| **Hog** | A busy-loop process that wants the CPU all the time. |
| **UART / serial console** | The emulated serial port QEMU connects to your terminal. The bridge types and reads through it. |
| **Bridge** | Host Python code that starts QEMU, sends a command line and collects the output. |
| **Sentinel / nonce** | A unique marker line (`@@DONE <random>`) printed when a command finishes, so the bridge knows where the output ends and cannot be fooled by echoed text. |
| **Allowlist** | List of permitted tools/paths; everything else is rejected. |
| **Prompt injection** | Text in untrusted data that tries to give instructions to the agent. |
| **TCG** | QEMU's software CPU emulation. Timing is approximate, so results are noisy. |
| **`-Werror`** | Compiler flag that turns warnings into errors. |

---

## 6. Repository layout and the living documents

**Principle: nothing is written "at the end".** The submission files exist from Stage 0 and each stage appends to them, then `tools/check_submission.sh <stage>` verifies that you are on track. At Stage 8 you only read through, fill the last blanks and run the packager.

```
repo/
├── xv6-public/               # the course tree + our changes (kernel, user programs, Makefile)
│   ├── sched_params.h        # team parameters (kernel + user)
│   └── sched_api.h           # structs shared by kernel and user (sched_stats, trace_ent, procstat)
├── host/                     # bridge/, planners/, validator.py, tools.py, audit.py, loop.py, agent.py, config.json, tests/
├── harness/                  # run_all.py, analyze.py
├── docs/
│   ├── JOURNAL.md            # one entry per stage: done / failed / why (mirrors commit notes)
│   ├── DESIGN.md             # data structures, algorithms, lock order, decisions (grows per stage)
│   ├── PARAMS.md             # team parameters and where they are defined
│   ├── SYSCALLS.md           # syscall number registry
│   ├── TEST_TABLE.md         # ONE table: every test, expected, observed, evidence path
│   ├── EVIDENCE_INDEX.md     # every graph/claim -> the raw log/CSV that produced it
│   ├── LIMITATIONS.md        # appended the moment you discover a limit
│   ├── REPORT_NOTES.md       # the 2-page report, drafted section by section with word budgets
│   ├── VIVA.md               # cheat sheet + drills, grows each stage
│   ├── CONTRIBUTIONS.md      # who did which files/functions (per person highlights)
│   ├── predictions.md        # written BEFORE the full measurement run (Stage 7)
│   └── gdb/                  # saved real GDB sessions
├── logs/                     # raw QEMU transcripts, audit.jsonl
├── results/                  # CSVs, graphs, Gantt charts
└── tools/                    # make_zip.sh, check_submission.sh
```

### Which stage touches which living document

| File | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
|---|---|---|---|---|---|---|---|---|---|
| JOURNAL.md | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| DESIGN.md | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | | final read |
| PARAMS.md | ✔ | | | | | | ✔ | ✔ | |
| SYSCALLS.md | | ✔ | ✔ | | | ✔ | ✔ | | |
| TEST_TABLE.md | | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | fill PENDING |
| EVIDENCE_INDEX.md | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | verify |
| LIMITATIONS.md | | | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | final read |
| REPORT_NOTES.md | | | ✔ | | ✔ | ✔ | | ✔ | polish |
| VIVA.md | | | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | drills |
| CONTRIBUTIONS.md | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | final |
| gdb/ | | | | | | ✔ (real bug) | | | verify |

### Rules that make this painless

1. **Every test is a row from the moment it is designed.** Columns: `ID | Stage | Test | Input | Expected | Observed | Evidence file | Type (positive / negative / benign control)`. The agent fills *Expected*; you run the test and replace `PENDING` in *Observed* the same day.
2. **Every raw log is registered** in `EVIDENCE_INDEX.md` the day it is created (path, what produced it, commit hash).
3. **Every limitation goes into `LIMITATIONS.md` the day you find it**, phrased as "what the model leaves out compared with a full implementation".
4. **Every 2 days:** commit, add a `JOURNAL.md` entry (what failed and why), run `tools/check_submission.sh <stage>`.
5. **REPORT_NOTES.md is already the 2-page report** in typed form, with word budgets: Model (120 words), Locking (100), Donation + proofs (150), Security (80), Results (150 + graphs), Problems (80), Limits (60). At the end you copy it by hand (the report must be handwritten).

### The packaging scripts (created in Stage 0, extended later)

- `tools/make_zip.sh <baseline_tag>`: zips only files **added or modified** since the baseline tag (`git diff --name-only --diff-filter=AM baseline HEAD`), excluding build outputs, into `dist/Team_Name_3.zip`. Run it at the end of **every** stage as a dry run. Surprises appear early.
- `tools/check_submission.sh <stage>`: checks that every document due by that stage exists, is non-empty, has no unfilled `TODO`/`<fill>` markers, that `TEST_TABLE.md` has no `PENDING` for tests belonging to completed stages, and prints a zip content summary.

---

## 7. Master context prompt (paste at the start of EVERY agent session)

````text
You are helping with an operating-systems course project (IIT Jodhpur CSL3030,
Project 3: "Deadline scheduler with priority donation through pipes").
It has two parts: kernel changes in xv6-public (x86, 32-bit, the course tarball
cs236-xv6-linux) and a host-side Python agent that drives xv6 through QEMU.

TREE FACTS (verify in the source before relying on them; ask me if unsure):
1. Compiler flags are -m32 -Wall -Werror: any warning (unused variable,
   missing prototype, signed/unsigned) breaks the build. Use 0, not NULL.
   There is no stdint.h/bool/uint64 in the kernel; use uint (32-bit).
2. Kernel print is cprintf(): only %d %x %p %s %c %%. No %u, %l, %lld.
3. User programs: #include "types.h" and "user.h"; printf(1, "...", ...)
   takes the fd first; exit() takes NO argument; wait() takes NO argument and
   returns a pid. User printf writes ONE CHARACTER per write() call, so output
   of concurrent processes interleaves; build a line in a buffer and emit it
   with a single write() when it must stay intact.
4. Adding a syscall touches: syscall.h (number), user.h (prototype), usys.S
   (SYSCALL(name)), syscall.c (extern int sys_name(void); plus table entry),
   and the implementation int sys_name(void) in sysproc.c (or proc.c).
   Arguments come from the user stack: argint(n,&v), argptr(n,(char**)&p,size),
   argstr(n,&s); each returns -1 on failure and the result must be checked.
   Number 22 is SYS_hello; new ones start at 23. Record in docs/SYSCALLS.md.
5. Adding user programs: add _name\ to UPROGS and name.c to EXTRA in the
   Makefile. Adding kernel files: add name.o to OBJS and declare shared
   functions in defs.h.
6. Locking: there is ONE global ptable.lock (in proc.c; the ptable struct is
   anonymous, so code that scans the process table must live in proc.c).
   sleep(chan, lk) / wakeup(chan) are the classic forms. Re-check wait
   conditions in a while loop. The scheduler holds ptable.lock across swtch.
7. LOCK ORDER (existing code already imposes it):
     tickslock -> ptable.lock      (clock interrupt calls wakeup)
     cons.lock -> ptable.lock      (console interrupt calls wakeup)
     pipe->lock -> ptable.lock     (sleep() inside pipe code)
   Therefore: NEVER call cprintf and NEVER acquire tickslock, cons.lock or a
   pipe lock while holding ptable.lock. To log from code holding ptable.lock,
   store the message in the trace ring or a small local array and print after
   releasing. Read ticks in such code with an unlocked volatile load
   (a 32-bit aligned read is atomic on x86).
8. ticks is a 32-bit uint and wraps. Compare deadlines with
   (int)(a - b) < 0, never plain <.
9. Team parameters live ONLY in sched_params.h (kernel/user) and
   host/config.json (host). Never hard-code them.
10. Changing FSSIZE/fs layout needs `make clean` before `make`.
11. Host security: never use eval, os.system or shell=True with model text.
    Only validated integers/enums may be interpolated into guest commands.
    Never commit API keys. The xv6 shell reads at most 99 chars per line;
    keep guest command lines under 90 chars.
12. Build and run: make qemu-nox CPUS=1 (add QEMU=/path/qemu-system-i386 if the
    config says so). Quit QEMU with Ctrl-A then X.

WORKING RULES:
- Do not guess. If a function, field or constant is not in the tree, say so.
- Minimal changes. List every file you create or modify, and the exact build
  and test commands.
- Add a short comment explaining every non-obvious design choice.
- DOCUMENTATION DUTY: at the end of the task, update the living documents I
  name (docs/DESIGN.md, TEST_TABLE.md, SYSCALLS.md, LIMITATIONS.md, ...).
  Fill the Expected column of new test rows and write PENDING in Observed.
  Never invent observed results, numbers, or log excerpts.
````

---

## 8. Part 1 (Days 1–10): foundations, agent, EDF

### Stage 0 (Days 1–3): reading, repo, parameters, submission scaffolding

**In plain words.**
Before coding you must understand how xv6 picks the next process, how a process sleeps and wakes, and how a pipe blocks. These three days are for reading and for building the *scaffolding*: the Git repo, the one file with your team's numbers, and the living documents plus the packaging scripts. That scaffolding is what makes the final submission a non-event.

**Technical details.**

*Reading list (xv6-public):* `proc.c` (`allocproc`, `scheduler`, `sched`, `yield`, `forkret`, `sleep`, `wakeup1`, `wakeup`, `kill`, `fork`, `exit`, `wait`), `proc.h`, `pipe.c`, `trap.c` (the timer case and the `yield()` at the end), `syscall.c`, `sysproc.c`, `usys.S`, `spinlock.c`, `file.h`, `file.c`, `param.h`, `lapic.c` (timer setup), `console.c`, `sh.c` (`runcmd`, the `PIPE` case, `buf[100]`), `Makefile`.

*What you must be able to explain afterwards (write the answers in `docs/DESIGN.md` under "Reading notes", with file and line numbers):*

1. How does `scheduler()` loop? In the stock code it runs **every** runnable process once per pass while holding `ptable.lock`, and `swtch` hands the CPU over with that lock still held (the process releases it later, in `yield`/`sleep`/`forkret`).
2. What do `sleep(chan, lk)` and `wakeup(chan)` do, and why must the caller hold `lk`?
3. Where does `piperead` block, and who wakes it?
4. How often does the timer fire, and why is `ticks` incremented only by CPU 0?
5. In `sh.c`, which process creates a pipe for `a | b`, and which processes inherit its ends? (This matters in Stage 5: the shell, not the writer, creates the pipe.)

*Team parameters.* Your instructor gives each team its own parameters (the handout: "per-team parameters... read them from one place"). Put them in `sched_params.h` and mirror them in `host/config.json`. Until you receive them use the placeholders below, clearly marked.

**Living documents to update.**

| File | What to write now |
|---|---|
| `docs/JOURNAL.md` | Stage 0 entry. |
| `docs/DESIGN.md` | Sections: *Reading notes* (answers above), *Lock order* (table from the master prompt, rule 7), *Capacity* (placeholder, filled in Stage 1). |
| `docs/PARAMS.md` | Table: parameter, value, source (who gave it, date), where defined. |
| `docs/CONTRIBUTIONS.md` | Names, roles, initial file ownership. |
| `docs/EVIDENCE_INDEX.md` | Header plus `logs/baseline_usertests.raw`. |
| Created empty with headers | `SYSCALLS.md`, `TEST_TABLE.md`, `LIMITATIONS.md`, `REPORT_NOTES.md` (with the word-budget skeleton), `VIVA.md`. |

**Manual steps (human only).**

1. Follow the setup document if not already done: QEMU built, `tar -zxvf cs236-xv6-linux.tgz`, `cd xv6-public`, `make clean && make`, `make qemu-nox`. Confirm `ls` works and `usertests` prints `ALL TESTS PASSED`.
2. Capture the baseline: `script -q logs/baseline_usertests.raw -c "make qemu-nox"`, type `usertests`, wait for `ALL TESTS PASSED`, exit with Ctrl-A X.
3. Create the repo: copy the tree in, add a `.gitignore` (`*.o *.d *.asm *.sym *.img _* kernel bootblock entryother initcode initcode.out mkfs vectors.S kernelmemfs dist/`), commit, then `git tag baseline`. Everything later is a diff against this tag.
4. Everyone sets their own Git identity (`git config user.name/user.email`).
5. Obtain the team parameters from the instructor. Do not invent them.
6. Read the files yourself and write the five answers in your own words.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 0: scaffolding only. Do NOT change any kernel logic.

1. Read proc.c, proc.h, pipe.c, trap.c, lapic.c, console.c, sh.c, param.h.
   Write docs/DESIGN.md section "Reading notes" answering with file:line
   references: (a) how scheduler() loops and what lock it holds across swtch;
   (b) sleep/wakeup semantics in this tree; (c) where piperead/pipewrite block
   and who wakes them; (d) the timer setup and why only CPU 0 increments
   ticks; (e) how sh.c builds a pipeline and which processes end up holding
   which pipe ends.
2. Create xv6-public/sched_params.h with commented placeholder defines
   (I will replace them): NO_DEADLINE 0xffffffff, MIN_SLACK 20, MAX_URGENT 8,
   NWF 8, TRACE_SIZE 256, MAX_HOGS 8. Create host/config.json with the same
   values plus keys: xv6_dir, qemu_bin (null by default), cpus_allowed [1,3],
   allowlist ["/report.txt","/inbox.txt","/README"], clamp false, W_ticks null.
   Create host/config.py that loads it.
3. Create the living documents listed in docs/ (section 6 of my plan) with
   headers and empty tables. TEST_TABLE.md columns: ID | Stage | Test | Input |
   Expected | Observed | Evidence file | Type. REPORT_NOTES.md must contain
   these headings with word budgets as comments: Model (120), Locking (100),
   Donation and proofs (150), Security (80), Results (150), Problems (80),
   Limits (60).
4. Create tools/check_submission.sh <stage>. Required files and the stage by
   which they must exist and be non-empty: JOURNAL, DESIGN, PARAMS,
   CONTRIBUTIONS (0); SYSCALLS, TEST_TABLE, EVIDENCE_INDEX (1); LIMITATIONS,
   REPORT_NOTES, VIVA (2); logs/audit.jsonl (3); at least one file in
   docs/gdb/ (5, warn only before 8); results/results.csv (7). It must also
   fail if any file due so far contains "TODO" or "<fill>", and if
   TEST_TABLE.md has PENDING in a row whose Stage <= the given stage.
   It then calls tools/make_zip.sh and prints the file list and size.
5. Create tools/make_zip.sh: uses the git tag "baseline", lists files added or
   modified (git diff --name-only --diff-filter=AM baseline HEAD) plus
   untracked new files, excludes build outputs, and writes
   dist/${TEAM:-Team_Name}_3.zip. Print the list and total size.
List every file you created.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-00a | `usertests` on the untouched tree | `ALL TESTS PASSED` (evidence: `logs/baseline_usertests.raw`) |
| T-00b | `tools/check_submission.sh 0` | passes |
| T-00c | `python -c "import host.config"` | loads without error |

**Commit note.**

```
stage0: baseline tag, scaffolding, living docs, packaging scripts
Learned: <tick period, ptable.lock held across swtch, ...>
Failed/confusing: <what you misread first>
```

**Definition of done.** `tools/check_submission.sh 0` is green and `dist/Team_Name_3.zip` builds.

---

### Stage 1 (Days 3–4): the `hello` syscall, bridge ping, capacity fixes

**In plain words.**
Prove the toolchain works. (1) Add the course's `hello()` system call; it is only there to show you know every file a syscall touches. (2) Write a small Python script that boots xv6 in QEMU, types `ls`, and prints the answer. (3) Fix two things that would bite later: the xv6 disk is too small for all our new programs, and we do not yet know how fast `ticks` really tick.

**Technical details.**

*How a syscall works on x86 (under the hood).* A user stub (generated by `usys.S`) puts the syscall number in `%eax` and executes `int $64`. The CPU jumps into the kernel, `trap()` is called, and `syscall()` in `syscall.c` indexes the `syscalls[]` table by that number and calls the C function. Arguments are not in registers: `argint(n,&v)` finds the n-th 32-bit value on the user stack at `esp + 4 + 4n`. The return value goes back in `%eax`.

*Steps (exactly as in the setup document, section 3):*

1. `syscall.h`: `#define SYS_hello 22`
2. `user.h`: `int hello(void);`
3. `usys.S`: `SYSCALL(hello)`
4. `syscall.c`: `extern int sys_hello(void);` and `[SYS_hello] sys_hello,` in the table
5. `sysproc.c`: `int sys_hello(void){ cprintf("hello from kernel\n"); return 0; }`
6. `hello_test.c` (prints `hello() returned %d`), then `_hello_test\` in `UPROGS` and `hello_test.c` in `EXTRA`

*Bridge (Milestone D of the agent guide).* `QemuBridge.start(cpus)` spawns `make qemu-nox CPUS=<n>` (plus `QEMU=<path>`) with `pexpect`, waits for `init: starting sh` and the `$ ` prompt, and `run_raw("ls")` sends one line and returns the text up to the next prompt. All raw bytes are logged. Notes: the console echoes what you type; lines end in `\r\n`; never assume one read returns a whole response.

*Capacity.* `sb: size 1000 nblocks 941`: the ~16 stock programs already use about 600 blocks. Add ten programs and `usertests` will fail with "out of blocks". Raise `FSSIZE` in `param.h` (for example 4000), then `make clean && make` (the Makefile does not track `param.h` for `fs.img`, so a stale image would silently stay small).

*Tick rate.* Do not assume 100 Hz. Write `user/ticktest.c` that calls `sleep(500)` and prints `uptime()` before/after; time it with a stopwatch or compare with `date` on the host. Record ticks per second in `PARAMS.md`. All later deadlines are in ticks.

**Living documents to update.**

| File | What to write now |
|---|---|
| `SYSCALLS.md` | Row: 22, `hello`, `int hello(void)`, `sysproc.c`, setup doc. |
| `DESIGN.md` | *Capacity*: old/new `FSSIZE` and why. *Clock*: measured ticks per second. *Bridge*: method (pexpect on serial console), prompt strings, line-length limit. |
| `TEST_TABLE.md` | T-01 to T-04 below. |
| `EVIDENCE_INDEX.md` | The raw log of the bridge ping and the `ticktest` capture. |
| `docs/bridge.md` | The documented bridge method (the agent guide requires it). |
| `JOURNAL.md`, `CONTRIBUTIONS.md` | Entries. |

**Manual steps (human only).**

1. Do the six `hello` edits by hand once. You will be asked in the viva which files a syscall touches.
2. Run `make clean && make && make qemu-nox`, type `hello_test`.
3. `pip install pexpect` inside a virtualenv.
4. Run the tick measurement yourself with a stopwatch.
5. Decide and write the exact QEMU launch line (`QEMU=` path if you built QEMU from source, `QEMUEXTRA=-snapshot` for reproducible runs; check your Makefile supports `QEMUEXTRA`).

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 1 task.

Part A: implement the hello syscall exactly as follows. SYS_hello is 22
(syscall.h). Add int hello(void); to user.h, SYSCALL(hello) to usys.S, the
extern and table entry to syscall.c, int sys_hello(void) in sysproc.c that
does cprintf("hello from kernel\n"); return 0;. Create hello_test.c that
prints "hello() returned %d" via printf(1, ...). Add _hello_test\ to UPROGS
and hello_test.c to EXTRA. Do NOT change mytest.

Part B: in param.h raise FSSIZE to 4000. Create ticktest.c: record uptime(),
sleep(500), print both values and the difference with printf(1,...).
Add to UPROGS/EXTRA. Remind me that make clean is required.

Part C: host/bridge/qemu_bridge.py with class QemuBridge:
- start(cpus=1): spawn "make qemu-nox CPUS=<cpus>" (add "QEMU=<qemu_bin>" and
  "QEMUEXTRA=-snapshot" only if host/config.json says so) with pexpect in
  config.xv6_dir, encoding utf-8 with codec_errors replace. Wait for
  "init: starting sh" then the prompt regex r"\$ " with a generous timeout.
- run_raw(cmd, timeout=15): verify len(cmd) < 90; send the line; wait for the
  next prompt; return the text between, with the echoed command line and \r
  removed.
- close(): send Ctrl-A then x, wait for exit, terminate(force=True) as fallback.
- Write every byte seen to logs/<timestamp>.raw via pexpect's logfile_read.
host/ping.py: start, run "ls", print the result, close.
Also write docs/bridge.md describing the method, prompts, limits.
Update docs: SYSCALLS.md (row for 22), TEST_TABLE.md rows T-01..T-04
(hello_test output; ls via Python; ticktest result; usertests after the
FSSIZE change) with Expected filled and Observed PENDING, DESIGN.md sections
Capacity and Bridge, EVIDENCE_INDEX.md placeholders for the logs.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-01 | `hello_test` in xv6 | prints `hello from kernel` then `hello() returned 0` |
| T-02 | `python host/ping.py` | prints the `ls` listing including `README`, `hello_test` |
| T-03 | `ticktest` | prints a tick difference of about 500; you compute ticks/second from the stopwatch |
| T-04 | `usertests` after `FSSIZE` change | `ALL TESTS PASSED` |
| T-05 *(negative)* | remove the `UPROGS` entry temporarily | `hello_test: not found`; restore |

**Commit note.**

```
stage1: hello syscall, QemuBridge ping, FSSIZE 4000, measured tick rate
Failed: <forgot usys.S entry -> link error / prompt regex hung / stale fs.img>
Measured: <N> ticks per second.
```

**Definition of done.** `tools/check_submission.sh 1` green.

---

### Stage 2 (Days 4–7): kernel foundation and baseline EDF

**In plain words.**
Teach xv6 about deadlines. Each process gets a "finish by" tick. The scheduler stops running ready programs in a circle and instead always picks the ready one with the nearest deadline. A process with no deadline counts as "never", so it only runs when no urgent process is ready. A switch (`setsched`) lets the same kernel behave as round-robin, EDF, or EDF with donation. **No donation yet**: debugging EDF and donation at once is what sinks this project.

**Technical details.**

*How the stock scheduler works (so you know what you are replacing).* Each CPU runs `scheduler()` forever: enable interrupts, take `ptable.lock`, walk the 64-slot table, and for every `RUNNABLE` process: mark it `RUNNING`, `switchuvm` (load its page table), `swtch` into it. When the process yields (timer interrupt), sleeps or exits, it `swtch`es back with `ptable.lock` still held, and the loop continues. So stock xv6 gives every runnable process one quantum (one tick) per pass: round-robin.

*EDF replacement.* For policy 1 and 2, do the same walk but only **select** the best candidate, then run just that one:

- **Effective deadline** `effective(p)` = the more urgent of `p->deadline` (own) and `p->donated` (lent by a waiter). They are separate fields so a donation can be withdrawn without losing the process's own deadline.
- **Wrap-safe compare** (absolute deadlines are ticks, which wrap):

```c
static int dl_before(uint a, uint b){          // true if a is more urgent than b
  if(a == NO_DEADLINE) return 0;
  if(b == NO_DEADLINE) return 1;
  return (int)(a - b) < 0;
}
```

- **Tie-break:** with strict `<` and many processes at `NO_DEADLINE`, the lowest table index always wins, so high-index processes (often `sh`) starve behind a hog. Break ties by smallest `last_run` (least recently run) and set `last_run = ++runcounter` when you schedule. Do not use `<=` (it just moves the starvation to the highest index).
- Every timer interrupt already calls `yield()`, so the choice is re-made every tick; a newly urgent process preempts within one tick.
- Policy 0 must run the original unmodified loop.

*Data structures (`proc.h`).* Add to `struct proc`: `int wid; uint deadline; uint donated; struct pipe *waiting_pipe; uint last_run; int missed;` and a forward declaration `struct pipe;`. Initialise in `allocproc`: deadline and donated `NO_DEADLINE`, others 0. `fork` copies `wid` and `deadline`; `exec` leaves them alone.

*Workflows.* `workflows[NWF]` (in `proc.c`, protected by `ptable.lock`): `wid`, `abs_deadline`, `nmembers`, `misses`, `rejected`. `setworkflow(wid, deadline_ticks)`: the first caller fixes `abs_deadline = now + deadline_ticks`; later callers join it. A second call by the same process returns -1 (documented). When a process exits it leaves its workflow (`nmembers--`, slot freed at zero), otherwise the table fills during long agent sessions.

*Syscalls (numbers from `SYSCALLS.md`):* `setsched(int policy)` = 23, `setworkflow(int wid, int deadline_ticks)` = 24, `schedinfo(struct sched_stats *dst)` = 25. `schedinfo` uses `argptr` then fills the struct; the shared struct lives in `sched_api.h`.

**Living documents to update.**

| File | What to write now |
|---|---|
| `DESIGN.md` | *Scheduler*: `effective()`, `dl_before` (with a worked wraparound example), tie-break and why `<=` is wrong, policy switch, workflows table and its lock. |
| `SYSCALLS.md` | Rows 23, 24, 25 with argument meaning, return values, error cases. |
| `TEST_TABLE.md` | T-06..T-13 below. |
| `REPORT_NOTES.md` | *Model*: `effective(p) = more urgent of (d, donated)`; EDF rule; preemption each tick. |
| `LIMITATIONS.md` | Global `ptable.lock` (coarse, fine for NCPU ≤ 8), one `setworkflow` per process, table size `NWF`. |
| `VIVA.md` | Q&A: why two fields; why tie-break; why wrap-safe compare. |
| `EVIDENCE_INDEX.md`, `JOURNAL.md`, `CONTRIBUTIONS.md` | Entries. |

**Manual steps (human only).**

1. Review the `scheduler()` diff line by line against the lock rules. Agents often forget that an idle CPU must still release `ptable.lock` and loop with `sti()`.
2. Run `edftest` on `CPUS=1` under `rr` and `edf` and **save both outputs** to `logs/`.
3. Run `usertests` three times (once per policy: type `schedctl edf` first in the same boot). It takes a while; read something meanwhile.
4. Boot once with `CPUS=3` to confirm no panic.
5. Decide the deadline unit semantics with the team and write them in `DESIGN.md`.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 2: baseline EDF with a runtime-switchable policy. NO donation yet.

1. sched_api.h (shared by kernel and user, no kernel-only includes):
   struct sched_stats { int policy; int ncpu; uint ticks; int misses;
   int donations; int cycles; int rejected; };
2. proc.h: add forward decl "struct pipe;" and fields int wid; uint deadline;
   uint donated; struct pipe *waiting_pipe; uint last_run; int missed; to
   struct proc. allocproc initialises deadline=donated=NO_DEADLINE, rest 0.
   fork() copies wid and deadline; donated starts NO_DEADLINE. exec untouched.
3. proc.c: globals int sched_policy (0 rr, 1 edf, 2 edf_donate) and
   uint runcounter. static dl_before(a,b) as specified in my plan.
   static effective(p). A helper now_ticks() = unlocked volatile read of
   ticks (do NOT take tickslock under ptable.lock).
4. scheduler(): policy 0 = ORIGINAL loop unchanged. Policies 1 and 2:
   for(;;){ sti(); acquire(&ptable.lock); scan all NPROC slots choosing best
   among RUNNABLE: better if dl_before(effective(p),effective(best)), or
   equal effective deadlines and p->last_run < best->last_run (never <=).
   If best: best->last_run = ++runcounter; then the same
   c->proc=best; switchuvm; state=RUNNING; swtch; switchkvm; c->proc=0 as
   the stock code. release(&ptable.lock); }
   Keep ptable.lock held from the scan through the swtch exactly like stock.
5. workflows[NWF] (struct {int wid; uint abs_deadline; int nmembers; int
   misses; int rejected;}) in proc.c, protected by ptable.lock.
   int sys_setworkflow(void): argint both args, reject wid<=0 or >=NWF-ish or
   deadline<=0 or a second call by the same process (return -1); first caller
   of a wid sets abs_deadline = now_ticks()+deadline; sets p->wid and
   p->deadline = abs_deadline. Add a stub admission_check_locked() returning 0.
   exit(): after acquiring ptable.lock call a helper wf_leave_locked(curproc)
   that decrements nmembers and frees the slot at zero.
6. int sys_setsched(void): policy 0..2 else -1.
   int sys_schedinfo(void): argptr(0, ..., sizeof(struct sched_stats)), fill
   (ncpu is the existing global).
7. Syscall numbers 23 setsched, 24 setworkflow, 25 schedinfo; do every file
   edit. Put sys_* in sysproc.c calling helpers exported through defs.h; the
   workflows table and policy live in proc.c.
8. User programs (add to UPROGS and EXTRA): schedctl.c (schedctl rr|edf|
   edf_donate), schedstat.c (print sched_stats), edftest.c: parent forks two
   children that each burn about 5 seconds of CPU; child A calls
   setworkflow(1,100) and child B setworkflow(2,200); each prints
   "child X pid=%d done at %d" (build the line in a buffer, ONE write()).
9. Docs: DESIGN.md (Scheduler section), SYSCALLS.md rows 23-25, TEST_TABLE.md
   rows T-06..T-13 (Expected filled, Observed PENDING), LIMITATIONS.md,
   REPORT_NOTES.md Model section, VIVA.md Q&A.
Give exact build/test commands. Do not touch pipe.c.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-06 | `schedctl edf; edftest`, `CPUS=1` | deadline-100 child finishes first |
| T-07 | `schedctl rr; edftest`, `CPUS=1` | both finish close together (contrast) |
| T-08 | `schedctl edf; usertests` | `ALL TESTS PASSED` (also exercises the tie-break) |
| T-09 | `schedctl rr; usertests` | `ALL TESTS PASSED` |
| T-10 | `schedctl edf_donate; usertests` (donation not written yet) | `ALL TESTS PASSED` |
| T-11 *(negative)* | `setsched(7)` | returns -1 |
| T-12 *(negative)* | `setworkflow(1,0)` and a second `setworkflow` call | -1 |
| T-13 | boot with `CPUS=3` | no panic |

**Commit note.**

```
stage2: runtime policy switch + baseline EDF (no donation)
Design: tie-break on least-recently-run (not <=) to avoid index starvation.
Failed: <e.g. idle CPU kept ptable.lock -> other CPU never scheduled>
Tests: edftest order OK CPUS=1; usertests OK rr/edf/edf_donate.
```

**Definition of done.** `tools/check_submission.sh 2` green.

---

### Stage 3 (Days 4–8, in parallel): the agent track

**In plain words.**
This is the agentic half. Think of a remote control: your Python program is the remote, the xv6 shell is the TV, and a bridge presses buttons and reads the screen. A *validator* is a bouncer: the planner (rules first, an LLM later) proposes a tool call such as `run_pipeline(stages=4, deadline=300)`, and the bouncer lets it through only if the tool is on the list and every number is in range. The bridge then types a **fixed command template** with only those validated numbers filled in. Text produced by a model is never typed into the guest. Every step is written to a log as evidence.

**Technical details.**

*Guest tools (C).*

- `xrun <nonce> cmd args...`: forks, `exec`s `cmd`, `wait()`s, then prints `@@DONE <nonce>`. Because xv6-public has no exit status, tools report success or failure in their own output (`RESULT ...`, `ERR ...`). If `exec` fails the child prints `@@EXECFAIL <nonce>`. The typed command line never contains the string `@@DONE`, so the console echo cannot fake completion.
- `wfgen` (stub now, real in Stage 6), `schedctl`, `schedstat`, `schedtrace` (already or soon exist).

*Bridge `run(argv)`.* Generate a random nonce, send `xrun <nonce> <argv...>`, assert the line is under 90 characters (the xv6 shell reads 99), verify the echo matches what you sent (retry or send with a tiny per-character delay if characters were dropped), then expect one of: `@@DONE <nonce>`, `@@EXECFAIL <nonce>`, `panic:`, `--kill proc` (a user process crashed), or timeout; after `@@DONE` also wait for the next prompt to resynchronise. Return `Observation(status, output, elapsed)`; on timeout or panic, mark it, save the log, restart QEMU, never invent success. `restart(cpus)` accepts only 1 or 3. A kernel panic freezes xv6 silently, so the **timeout** is how you detect a hung guest.

*Tool registry and validator.*

| Tool | Guest command (fixed template) | Constraints |
|---|---|---|
| `list_files()` | `ls` | none |
| `read_file(path)` | `cat <path>` | regex `^/?[A-Za-z0-9._]{1,14}$` (xv6 names are at most 14 chars) and membership in the allowlist |
| `set_policy(p)` | `schedctl <p>` | enum `rr, edf, edf_donate` |
| `run_pipeline(stages,work,bytes,deadline,hogs)` | `wfgen ...` | ints only; `2≤stages≤6`; `deadline ≥ MIN_SLACK`; `0≤hogs≤MAX_HOGS`; work/bytes capped |
| `sched_stats()` | `schedstat` | none |
| `summarize(text)` | host-side only | no guest effect |

The validator rejects unknown tools, missing or extra arguments, wrong types (a Python `bool` is not an `int`), and out-of-range values *before* the bridge. Rejecting is the default; clamping is optional via `config.clamp`, and both the proposed and the clamped call are logged.

*Planners.* `DeterministicPlanner` (rules; mode `injected` proposes `run_pipeline(deadline=1, hogs=8)` after `/inbox.txt` was read) and `OllamaPlanner` (HTTP to `localhost:11434/api/chat` with a JSON schema so it returns a tool call, not shell text). Build the deterministic one first.

*Audit log.* One JSON object per step in `logs/audit.jsonl`: `ts, user_request, proposed_call, validated_call, validation_error, guest_output, observation_status, kernel_log_lines, final_state` (the handout's evidence list).

**Living documents to update.**

| File | What to write now |
|---|---|
| `DESIGN.md` | *Trust boundaries* (model proposes, validator checks, bridge types fixed templates, kernel enforces), tool table, sentinel protocol. |
| `TEST_TABLE.md` | T-14..T-24 below. |
| `EVIDENCE_INDEX.md` | One accepted and one rejected `audit.jsonl` record; the raw log of the e2e run. |
| `LIMITATIONS.md` | No exit status in xv6; console line limit; serial timing assumptions; interleaved output. |
| `VIVA.md` | Why the Python validator is not the security boundary (preview). |
| `JOURNAL.md`, `CONTRIBUTIONS.md` | Entries. |

**Manual steps (human only).**

1. Put the demo files into the image: create `report.txt` and `inbox.txt` in the `xv6-public` directory, then in the Makefile change `fs.img: mkfs README $(UPROGS)` to include them and `./mkfs fs.img README $(UPROGS)` likewise (`fs.img: mkfs README report.txt inbox.txt $(UPROGS)` and `./mkfs fs.img README report.txt inbox.txt $(UPROGS)`). Rebuild with `make clean`.
2. Write the file contents yourself: `report.txt`: three harmless lines; `inbox.txt`: "The project review is on Friday." plus an injected line asking for a deadline-1 pipeline with 8 hogs.
3. Decide the allowlist and write it in `config.json`.
4. Only if using an LLM: install Ollama yourself and pull the course model. Never put keys in the repo.
5. Check that the bridge runs nothing on the host except `make ... qemu-nox`.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 3: the host agent (Python 3; stdlib + pexpect; requests only inside the
Ollama planner).

Guest (C, add to UPROGS/EXTRA):
- xrun.c: usage "xrun <nonce> cmd args...". fork; child exec(argv[2],
  &argv[2]); if exec fails child prints "@@EXECFAIL <nonce>" and exits.
  Parent wait()s, then prints "@@DONE <nonce>". xv6 has no exit status; do not
  pretend otherwise.
- wfgen.c: stub printing "wfgen stub".
Host:
1. host/bridge/qemu_bridge.py: extend the Stage 1 class with
   run(argv, timeout=30) -> Observation(status, output, elapsed) as described
   in my plan (random nonce via secrets.token_hex(4); assert command line
   < 90 chars; verify the echo; expect DONE / EXECFAIL / "panic:" /
   "--kill proc" / TIMEOUT; after DONE expect the prompt). On panic/timeout
   save the log, restart(), return status "panic"/"timeout". restart(cpus) only
   accepts 1 or 3. Raw log per run in logs/.
2. host/tools.py: TOOLS registry as in my table: argument specs, a function
   building the guest argv from VALIDATED values only, host_only flag.
3. host/validator.py: validate_action(action) rejecting unknown tool, missing
   or extra args, wrong types (bool is not int), out-of-range; optional
   clamp mode driven by config; returns validated action or raises
   ValidationError(reason).
4. host/planners/base.py, deterministic.py (modes normal/injected),
   ollama_planner.py (not used by default; JSON schema constrained output).
5. host/audit.py writing logs/audit.jsonl with the fields in my plan;
   collect kernel_log_lines = console lines starting with "donate:", "admit:",
   "sched:".
6. host/loop.py + host/agent.py: plan -> validate -> execute -> observe, max 8
   steps. CLI: python host/agent.py "<request>" [--planner ...] [--mode ...].
7. host/tests/test_validator.py (pytest): unknown tool, missing arg, extra
   arg, "../x", "/a/b", 20-char name, wrong type, bool as int, deadline below
   MIN_SLACK, hogs=99, one valid call.
8. Update docs: DESIGN.md (Trust boundaries, tool table, sentinel protocol),
   TEST_TABLE.md rows T-14..T-24, LIMITATIONS.md, EVIDENCE_INDEX.md
   placeholders, VIVA.md.
Show commands for the unit tests and an end-to-end example.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-14 | `python host/agent.py "list files then read /report.txt"` | listing and file contents returned, audit lines written |
| T-15 *(negative)* | planner proposes `rm_all` | rejected before the bridge, no QEMU traffic |
| T-16 *(negative)* | `read_file("../etc/passwd")` | rejected |
| T-17 *(negative)* | `read_file("/a/b")`, 20-char name | rejected |
| T-18 *(negative)* | `read_file("/notinallowlist")` | rejected |
| T-19 *(negative)* | `run_pipeline(deadline=1)` | rejected by validator |
| T-20 *(negative)* | `run_pipeline(hogs=99)` | rejected |
| T-21 *(negative)* | missing arg / extra arg / `True` as int | rejected |
| T-22 | forced timeout (a command that never prints `@@DONE`) | `status=timeout`, VM restarted, no invented success |
| T-23 | `xrun` of a missing program | `@@EXECFAIL`, status reported as error |
| T-24 | `pytest host/tests` | all pass |

**Commit note.**

```
stage3: host agent (bridge, validator, deterministic planner, audit log)
Design: xrun sentinel with random nonce so echoed input cannot fake completion.
Failed: <echo matched regex early / shell line limit / dropped characters>
Tests: validator <n>/<n>, e2e list+read OK, timeout handled.
```

**Definition of done.** `tools/check_submission.sh 3` green (it now also requires `logs/audit.jsonl`).

---

### Stage 4 (Days 8–10): integration, admission control, injection demo, Day-10 checkpoint

**In plain words.**
Join the two tracks: the agent picks a policy, launches a small pipeline, and gets back "finished at tick X, deadline Y, miss or not". Then add the **safety gate inside the kernel**: it refuses silly deadlines (1 tick) and refuses too many urgent processes. Finally, stage the attack: the inbox file tells the agent to start a deadline-1 pipeline with 8 hogs. Show the validator stops it, **and** show that if you skip the agent and type the same command at the xv6 shell yourself, the kernel still says no. That second part is the course's central point.

**Technical details.**

- **Admission control** in `setworkflow` (under `ptable.lock`): reject (return -1, count `rejected`) if `deadline_ticks < MIN_SLACK`, or if granting would make the number of live processes with a finite deadline exceed `MAX_URGENT`. Print one line `admit: rejected pid=%d wid=%d deadline=%d reason=slack|urgent` **after** releasing `ptable.lock` (never `cprintf` under it; see lock order).
- **Firm deadlines.** During every scheduler scan, a process whose own deadline is overdue (`(int)(now - deadline) > 0`) is counted as a miss once (`missed` flag, workflow `misses++`) and from then on treated as `NO_DEADLINE` by `effective()`. Without this an overdue hog has the earliest deadline forever and starves everything (the EDF "domino effect"). Also count it in `exit()` in case the scan never saw it overdue.
- **Fork note.** Children inherit deadlines but `MAX_URGENT` is only checked at `setworkflow`; record this in `LIMITATIONS.md`.
- **Minimal `wfgen`** (2 stages) so the agent has something real to launch: stage 2 calls `setworkflow(1, D)`, reads a pipe fed by stage 1, then prints one `RESULT` line.
- **Injection demo.** Inbox text asks for the attack. `DeterministicPlanner` in `injected` mode follows it. Layer 1 (validator) rejects or clamps; record proposed vs validated. Layer 2: you type `wfgen 3 200 4096 1 8` yourself at the xv6 prompt and the kernel prints `admit: rejected`. Benign control: a legitimate deadline succeeds.

**Day-10 checkpoint (must hold, otherwise cut scope that day):** the agent runs end to end; EDF works on `CPUS=1` in the happy path; admission control rejects deadline 1; `usertests` passes.
*If behind:* drop the Ollama planner and the `wait()` donation stretch; keep the deterministic planner, EDF and the donation core.

**Living documents to update.**

| File | What to write now |
|---|---|
| `DESIGN.md` | *Admission control and firm deadlines*, the injection scenario and the two layers. |
| `TEST_TABLE.md` | T-25..T-33 below. |
| `REPORT_NOTES.md` | *Security*: two layers, why the second matters. |
| `LIMITATIONS.md` | Fork-inherited deadlines; `MAX_URGENT` is a global cap, not per user; firm deadlines hide late work from EDF. |
| `EVIDENCE_INDEX.md` | The injected-run audit record; console capture of the manual shell bypass. |
| `VIVA.md` | "Why is the Python validator not security?" full answer. |
| `JOURNAL.md`, `CONTRIBUTIONS.md` | Entries including the Day-10 checklist. |

**Manual steps (human only).**

1. Run the injection demo yourself, live, watching the console, at least once.
2. Run the shell bypass **by hand**. Do not delegate it to the agent.
3. Decide reject vs clamp and write it in `DESIGN.md` (reject is cleaner).
4. Confirm `MIN_SLACK` agrees between `sched_params.h` and `config.json`.
5. Re-run `usertests` under all three policies.
6. Fill the Day-10 checklist in `JOURNAL.md` honestly. If any item is red, write what you cut and why.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 4: integration, admission control, firm deadlines, injection demo.

Kernel (proc.c; syscall in sysproc.c):
1. Replace the admission_check_locked stub: reject when deadline_ticks <
   MIN_SLACK or when the count of live (non-UNUSED, non-ZOMBIE) processes
   with deadline != NO_DEADLINE would exceed MAX_URGENT. On rejection set a
   reason code, increment the workflow/global rejected counter, RELEASE
   ptable.lock, then cprintf one line:
   "admit: rejected pid=%d wid=%d deadline=%d reason=%s\n". Never cprintf
   while holding ptable.lock.
2. Firm deadlines: in the scheduler scan, for every non-UNUSED process with a
   finite own deadline that is overdue by (int)(now_ticks()-deadline) > 0 and
   !missed: set missed=1 and increment the workflow miss counter and the
   global miss counter (exposed in sched_stats.misses). effective() must
   return NO_DEADLINE for a process with missed set. exit() also counts an
   overdue, not-yet-missed process.
User:
3. Real minimal wfgen.c (2 stages, usage: wfgen <stages> <work> <bytes>
   <deadline> <hogs>; stages other than 2 may print "unsupported" for now):
   parent creates one pipe and forks hogs first (busy loops, no workflow),
   records t_start=uptime(), forks stage 1 (writes <bytes> in 64-byte chunks
   with <work> busy-loop units between writes, closes unused fds) and stage 2
   (closes unused fds, calls setworkflow(1, deadline) FIRST; if it returns -1
   print "wfgen: workflow rejected by kernel" and exit; otherwise reads until
   EOF burning <work> units per chunk, then builds
   "RESULT policy=%d cpus=%d finish=%d deadline=%d miss=%d\n" in a buffer
   and emits it with ONE write()). Parent closes its pipe ends, waits for
   both stage pids, kills and reaps the hogs. Only the LAST stage calls
   setworkflow.
Host:
4. Add report.txt/inbox.txt to the image (show the Makefile change). inbox.txt
   contains a benign line and an injected instruction to run a pipeline with
   deadline 1 and 8 hogs.
5. Planner mode "injected" proposes that call after /inbox.txt was read.
   Validator reject-or-clamp via config; log proposed and validated calls.
6. host/demos/injection_demo.py: (a) benign: set_policy edf then run_pipeline
   deadline 300 -> success, RESULT parsed into the observation; (b) injected
   scenario -> validator blocks; (c) prints the exact line I must type
   manually at the xv6 prompt for the bypass; (d) a helper that, after I type
   it, reads the raw log and reports whether an "admit: rejected" line
   appeared.
7. Update docs: DESIGN.md, TEST_TABLE.md rows T-25..T-33, REPORT_NOTES.md
   Security, LIMITATIONS.md, VIVA.md.
Do not modify pipe.c. Give exact test commands.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-25 | agent: `set_policy edf` then `run_pipeline` (2 stages, deadline 300), `CPUS=1` | `RESULT` line with finish, deadline, miss |
| T-26 *(negative)* | injected agent run | validator blocks; no hogs started |
| T-27 *(negative)* | **manual**: `wfgen 3 200 4096 1 8` at xv6 prompt | `wfgen: workflow rejected by kernel` and kernel `admit: rejected ... reason=slack` |
| T-28 *(benign control)* | manual: legitimate deadline | accepted, `RESULT` printed |
| T-29 *(negative)* | more than `MAX_URGENT` urgent processes | extra ones rejected, `reason=urgent` |
| T-30 | overdue process | counted as one miss, then treated as best-effort |
| T-31 | `usertests` under rr / edf / edf_donate | all pass |
| T-32 | `CPUS=3` pipeline run | no panic |
| T-33 | Day-10 checklist | all items ✔ or a documented cut |

**Commit note.**

```
stage4: integration + kernel admission control + firm deadlines + injection demo
Result: validator blocks deadline=1; kernel ALSO blocks it when typed at the shell.
Failed: <e.g. cprintf under ptable.lock -> deadlock with console interrupt>
Day-10 checkpoint: agent e2e OK, EDF CPUS=1 OK, admission OK, usertests OK.
```

**Definition of done.** `tools/check_submission.sh 4` green.

---

## 9. Part 2 (Days 11–20): donation, harness, evidence

### Stage 5 (Days 11–13): priority donation (the technically deep part)

**In plain words.**
Picture a relay team. The last runner (stage 4) is urgent but standing still, waiting for the baton from runner 3, who waits for runner 2, and so on. Donation says: "the waiting runner passes his urgency back to whoever has to hand him the baton". Then the whole chain outranks the lazy hog.

Three things make it tricky:

1. **Who is the writer of a pipe?** In a shell pipeline the shell creates the pipe and the children simply inherit its ends. When a reader first sleeps there is no single "writer process" to point at. So we **look through every process's open files** to find who still holds the write end.
2. **Chains and cycles.** Donation must travel several hops, but two processes can wait on each other, which would loop forever. We mark visited processes and stop on a repeat.
3. **Taking donations back.** When data arrives the donation must disappear, but if two readers donated to one writer, removing one must not remove the other. The simple fix: whenever something changes, wipe all donations and recompute them from the processes that are *currently* waiting.

**Technical details.**

*Why not a single `pi->writer` pointer (the handout's skeleton)?* In `sh.c` the process that runs `a | b` calls `pipe()` and forks both sides; neither side "owns" the pipe, and the pointer would be empty or stale (a dead process's slot gets reused). The truthful definition: **a holder of pipe P is any live process with an open `struct file` of type `FD_PIPE`, `f->pipe == P` and `f->writable`.** Scanning `NPROC × NOFILE` = 1024 slots is cheap.

*Hygiene matters.* Every stage of `wfgen` must close the pipe ends it does not use, and the parent must close all its copies after forking. Otherwise extra processes count as holders (over-donation) and EOF never arrives. The same hygiene is why the approach is an over-approximation: a process that merely *holds* the write end gets the donation even if it never writes.

*Locking (now much simpler than riscv).* All of this runs under the single `ptable.lock`. Entry points called from `piperead` hold `pipe->lock`, then take `ptable.lock`: that is the existing order. Reading another process's `ofile[]` is technically unsynchronised (xv6 does not protect it with `ptable.lock`); a stale read can only cause a momentary over- or under-donation, which the next recompute corrects. Write this down in `LIMITATIONS.md` as a *benign race*. **No `cprintf` under `ptable.lock`**: collect donation events in a small local array and print after releasing it (still holding `pipe->lock` is fine).

*Hooks.*

- In `piperead`, where the reader finds the pipe empty and `writeopen` is still set: call `pipe_wait_begin(pi)` **before** `sleep()` (both the pipe lock stays held, so no wakeup can be lost). It takes `ptable.lock`, sets `myproc()->waiting_pipe = pi`, and runs the donation walk. Right after `sleep()` returns call `pipe_wait_end()`: take `ptable.lock`, clear `waiting_pipe`, run recompute. This also covers the killed-while-sleeping path (the loop sees `killed` after waking).
- In `exit()` (after `ptable.lock` is held, files already closed): clear `waiting_pipe`, `wf_leave`, run recompute.
- `kill()` only marks the process; the donor's donation is removed when it wakes and exits.

*Donation walk (DFS with colours).* Start from the reader `q` with deadline `dl = effective(q)` (skip if `NO_DEADLINE`). For each holder `h` of `q->waiting_pipe` (`h != q`): if `dl_before(dl, h->donated)` set `h->donated = dl` and record a `DONATE` event. If `h->waiting_pipe` is set, continue from `h`. Use an explicit stack and a colour per process: *white* = unseen, *gray* = on the current path, *black* = finished. Reaching a gray process means a **cycle**: record `CYCLE`, increment the counter, do not follow it. Reaching a black process is just a second path (not a cycle); skip it. Also bound the depth by `NPROC` as a second safety net.

*Withdrawal by full recompute (N3).* Pass 1: set every live process's `donated = NO_DEADLINE`. Pass 2: repeat until nothing changes (at most `NPROC+1` rounds): for every process `q` with `waiting_pipe` set and a finite `effective(q)`, for each holder `h` of that pipe, `h->donated = more urgent of (h->donated, effective(q))`. Because `donated` values only ever move to more urgent values within a finite set, the loop terminates even on cycles. It correctly restores a second donor when the first leaves. Justify the choice in the report: simplicity and obvious correctness versus an `O(rounds × NPROC × NOFILE)` cost that is irrelevant at `NPROC = 64`.

*Debug mode.* `tracectl` command toggles printing of `donate: donor=<pid> recv=<pid> dl=<hex>` (use `%x`, `cprintf` has no `%u`).

*Extra syscall for tests.* `procinfo(int pid, struct procstat *dst)` = 28 returns `{state, deadline, donated, waiting}` so tests can assert withdrawal.

**Living documents to update.**

| File | What to write now |
|---|---|
| `DESIGN.md` | *Donation*: holder definition, walk pseudocode, colours, recompute, hooks, **lock-order argument** (why no path takes the locks in reverse), deferred printing rule. |
| `REPORT_NOTES.md` | *Locking* (order and why `cons.lock`/`tickslock` are never taken under `ptable.lock`), *Donation and proofs*: termination of recompute (monotone values on a finite set), cycle bound (colours plus depth `NPROC`), why a scan beats a writer pointer. |
| `SYSCALLS.md` | Row 28 `procinfo` (and `tracectl` if added now). |
| `TEST_TABLE.md` | T-34..T-45 below. |
| `LIMITATIONS.md` | Over-approximate holders; benign race on `ofile`; donation only through pipes (not `wait`, locks, files); `O(NPROC·NOFILE)` scan per event. |
| `docs/gdb/` | Your **real** GDB session (see manual step 6). |
| `VIVA.md` | Drills: donation through `wait()`, move the cycle check, change to a donor list. |
| `EVIDENCE_INDEX.md`, `JOURNAL.md`, `CONTRIBUTIONS.md` | Entries. |

**Manual steps (human only).**

1. **On paper first:** draw the 4-stage pipeline: which process sleeps on which pipe, who holds each write end, where donation flows. You must be able to redraw it at the viva. Photograph it for the report.
2. Run the 4-stage test under `edf` first and **watch it fail** (save the log). Then `edf_donate` and watch it succeed.
3. Review every exit path of `piperead`, `pipe_wait_begin/end`, and `exit()` for a lock that is not released and for a stale `waiting_pipe`. Agents routinely miss early returns.
4. Verify the lock order yourself by reading, not by trusting the agent: `pipe->lock → ptable.lock` allowed; nothing may take `pipe->lock`, `cons.lock` or `tickslock` while holding `ptable.lock`.
5. Test a cycle by hand with two processes and two pipes. The two test processes deadlock by design, so the test program must `kill` them after a timeout.
6. When something hangs (it will), use GDB and **save the session**: `make qemu-nox-gdb CPUS=1`, in another terminal `gdb -x .gdbinit kernel` (if GDB refuses to load `.gdbinit`, add `set auto-load safe-path /` to `~/.gdbinit`). Useful: `b scheduler`, `bt`, `p ptable.proc[3]`, `info threads` (each CPU is a thread). The rubric requires one *real* bug found and fixed; do not fabricate one.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 5: priority donation through pipes. Active only when sched_policy == 2.
Files: proc.c, proc.h, pipe.c, defs.h, sysproc.c, syscall.*, user tests.
All scan/donation code lives in proc.c (ptable is anonymous there).
proc.c needs these includes before using struct file fields: fs.h,
sleeplock.h, file.h (in that order after spinlock.h).

1. Holder definition: process q (state not UNUSED) is a holder of pipe pi iff
   some q->ofile[i] has type==FD_PIPE, pipe==pi and writable. Implement
   static int holds_write_end(struct proc *q, struct pipe *pi). Reading ofile
   without extra locks is a known benign race; add a comment saying so.
2. Public functions (declare in defs.h):
   void pipe_wait_begin(struct pipe *pi);  // called by piperead holding
        // pi->lock, just before sleep()
   void pipe_wait_end(void);               // called right after sleep()
   Both acquire/release ptable.lock internally (allowed: pipe->lock is
   already held, order is pipe->lock -> ptable.lock).
   pipe_wait_begin: set myproc()->waiting_pipe = pi; if sched_policy==2 and
   effective(myproc()) != NO_DEADLINE run the donation walk below.
   pipe_wait_end: clear waiting_pipe; if sched_policy==2 run recompute.
3. Edit piperead (and nothing else in pipe.c): in the wait loop, call
   pipe_wait_begin(p) immediately before sleep(&p->nread,&p->lock) and
   pipe_wait_end() immediately after it returns, on every iteration, before
   the killed check.
4. Donation walk (static, ptable.lock held): iterative DFS with an explicit
   stack of at most NPROC entries and a colour array (0 white, 1 gray,
   2 black) indexed by process slot. For reader q with deadline dl: for each
   holder h != q: if dl_before(dl, h->donated) { h->donated = dl; log DONATE }
   then if h->waiting_pipe is non-null recurse into h's pipe using dl. Reaching
   a gray process = cycle: log CYCLE, cycles++, do not follow. Black = skip.
   Depth also capped at NPROC.
5. recompute_donations_locked(): pass 1 sets donated=NO_DEADLINE for all
   non-UNUSED processes; pass 2 loops at most NPROC+1 rounds until no change:
   for every q with waiting_pipe != 0 and effective(q) != NO_DEADLINE, for
   each holder h of q->waiting_pipe (h != q) make h->donated the more urgent
   of itself and effective(q). Call it from pipe_wait_end and from exit()
   (after ptable.lock is acquired; also clear waiting_pipe there).
6. Event logging WITHOUT printing under ptable.lock: write events into a
   small static array (or the Stage 6 trace ring later) and, if debug is on,
   print them with cprintf AFTER releasing ptable.lock, still inside
   pipe_wait_begin/end: "donate: donor=%d recv=%d dl=%x\n",
   "donate: cycle\n". Debug toggle via tracectl(4 on / 5 off) or a debug
   global set by a new syscall; counters donations and cycles go into
   sched_stats.
7. Syscall 28 procinfo(int pid, struct procstat *dst) with struct procstat
   {int state; uint deadline; uint donated; int waiting;} in sched_api.h;
   return -1 if pid not found.
8. User tests (add to UPROGS/EXTRA), each with hygiene: every child closes
   pipe ends it does not use; parent closes all after forking:
   - donatetest.c: 4-stage chain (stage 1 writes more than 512 bytes in
     chunks), stages 2-3 forward, stage 4 calls setworkflow(1, D) first and
     reads to EOF; one hog without workflow; prints one RESULT line.
   - donate5.c: same with 5 stages and one hog.
   - cycletest.c: two processes each read the pipe the other writes; parent
     sleeps then kills both; expect exactly one "donate: cycle" and no hang.
   - killtest.c: a donor sleeping on a pipe is killed while donation is
     active; afterwards the receiver's donated (via procinfo) must be
     NO_DEADLINE; and a variant with two donors where one is killed and the
     other donation must remain.
9. Update docs: DESIGN.md (Donation + lock-order argument), REPORT_NOTES.md
   (Locking, Donation and proofs), LIMITATIONS.md, SYSCALLS.md, VIVA.md,
   TEST_TABLE.md rows T-34..T-45. Observed stays PENDING.
Tell me exactly how to run each test on CPUS=1 and CPUS=3. List every place
where a lock is acquired so I can verify the order.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-34 | 4-stage chain + 1 hog, `edf`, `CPUS=1` | last stage misses |
| T-35 | same, `edf_donate` | meets deadline; debug lines show the chain stage 3 → 2 → 1 |
| T-36 | 5-stage chain + unrelated hog (hidden-test category) | same improvement |
| T-37 | two readers donate to one writer, one reader finishes | remaining donation preserved (`procinfo`) |
| T-38 | pipe cycle between two processes | exactly one `donate: cycle`, no hang |
| T-39 | donor killed while donation active | receiver's `donated` returns to `NO_DEADLINE` |
| T-40 | two donors, one killed | other donation remains |
| T-41 | `usertests` under `edf_donate` | all pass |
| T-42 | `donatetest` on `CPUS=3` | no panic, no deadlock |
| T-43 *(negative)* | policy `rr` or `edf` | `donate:` lines never appear |
| T-44 | pipeline with `bytes < 512` | no blocking, no donation (documented sanity check) |
| T-45 | stress: 20 consecutive runs | no hang, no panic |

**Commit note.**

```
stage5: pipe donation via fd-table scan, DFS cycle detection, fixpoint withdrawal
Why not pi->writer: shell creates pipes; pointer is null at first block and can dangle.
Failed: <donate walk hung with interrupts off / lock leak on early return /
         cprintf under ptable.lock deadlocked -> deferred printing; GDB log: docs/gdb/<file>>
Tests: chain/cycle/kill OK; usertests OK under edf_donate.
```

**Definition of done.** `tools/check_submission.sh 5` green, and `docs/gdb/` has a real session.

---

### Stage 6 (Days 13–14): workload generator, trace ring, unattended harness

**In plain words.**
Build the experiment machine: (1) a workload program that makes pipelines of any length with any amount of CPU work and optional hogs; (2) a flight recorder in the kernel (who ran on which CPU, when, plus donation events) so you can draw a timeline; (3) a Python script that runs all the experiments by itself overnight: three policies × two CPU counts × twenty runs, restarting QEMU when it crashes.

Two rules make or break the experiment:

- Only the **last** stage sets the deadline. If every stage had it, plain EDF would already work and donation would look useless.
- Stages must really block, and hogs must outnumber CPUs. Otherwise nobody competes and you measure nothing.

**Technical details.**

*`wfgen` (full).* Usage `wfgen <stages 2..6> <work> <bytes> <deadline> <hogs>`. Parent: create `stages-1` pipes, fork hogs first, record `t_start = uptime()`, fork stage 1..S. Stage 1 writes `bytes` in 64-byte chunks with `work` busy-loop units between writes. Middle stages read a chunk, burn `work`, write. The **last stage only** calls `setworkflow(1, deadline)` first, reads to EOF burning `work` per chunk, then prints one `RESULT policy=.. cpus=.. finish=.. deadline=.. miss=..` line in a **single `write()`** (xv6 `printf` writes one character at a time; concurrent processes would interleave). `finish` is `uptime() - t_start`; `miss = finish > deadline` (the kernel's own miss counter is reported by `schedstat` as a cross-check). Every stage closes pipe ends it does not use; the parent closes all after forking, waits for the stage pids, then `kill`s and reaps the hogs. `bytes ≥ 4 × PIPESIZE (512)` guards against a workload that never fills a pipe. Hogs ≥ `cpus + 1`.

*Calibration.* `calib.c` runs the busy loop for N iterations and prints the tick delta; choose `work` so that one unloaded run takes a known `W` ticks (for example 40 to 60). Record `W` in `PARAMS.md` and `config.json`.

*Trace ring.* Per-CPU array of `TRACE_SIZE` entries `{uint tlo, thi; short cpu; short pid; short ev; int arg; uint seq;}`. Events: `SWITCH_IN`, `SWITCH_OUT`, `DONATE`, `WITHDRAW`, `CYCLE`, `DEADLINE_MISS`. Timestamps come from `rdtsc` (add `static inline unsigned long long rdtsc(void)` using `asm volatile("rdtsc" : "=A"(x))` to `x86.h`; verify in QEMU that it is monotonic; if not, order by `seq`). Every call site already holds `ptable.lock`, so no extra lock is needed; the ring is per CPU so consumers can see per-CPU order. Syscalls: `schedtrace(struct trace_ent *dst, int max)` = 26 (`argptr` with `max*sizeof`) and `tracectl(int cmd)` = 27 (on, off, clear, debug on/off). Python `plot_gantt.py` draws one lane per CPU with donation markers (ticks are too coarse for a Gantt; `rdtsc` is not).

*Harness.* For each (policy ∈ {rr, edf, edf_donate}) × (CPUS ∈ {1,3}) × run 1..20: restart (QEMU with `-snapshot` so each boot is pristine), `set_policy`, `run_pipeline` with `D = round(α·W)`, parse the `RESULT` line with a strict regex, append a CSV row, save the raw log. It must resume after a crash, record `status=timeout/panic` rows instead of aborting, and include the git commit hash in every row.

*Your own hidden-test categories (already covered in Stage 5, now automated):* 5-stage chain with a hog, pipe cycle, donor killed while donating.

**Living documents to update.**

| File | What to write now |
|---|---|
| `DESIGN.md` | *Workload design*, *Trace ring* (event list, locking, timestamps), *Harness* (resume logic, snapshot). |
| `PARAMS.md` | `W`, `α` values, `bytes`, `work`, hogs per CPU count. |
| `SYSCALLS.md` | Rows 26, 27. |
| `TEST_TABLE.md` | T-46..T-53 below. |
| `EVIDENCE_INDEX.md` | Calibration table, dry-run CSV, first Gantt chart. |
| `LIMITATIONS.md` | Timer nondeterminism under TCG; ring wraps and drops oldest; `rdtsc` assumptions. |
| `VIVA.md` | How to add a trace event; where timestamps come from. |

**Manual steps (human only).**

1. Calibrate `work`: run `wfgen` with 0 hogs on `CPUS=1` five times and record mean and spread. Write `W`.
2. Choose hogs: at least `cpus + 1` (2 or 3 for `CPUS=1`, 4 or 5 for `CPUS=3`).
3. Run the harness with `--dry-run` (2 runs per cell) before the full batch.
4. Inspect one Gantt chart by eye. If donation markers do not line up with the chain, the trace has a bug.
5. Note the commit hash used; do not rebuild between runs of the same batch.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 6: workload generator, trace ring, plotting, harness.

Kernel:
1. x86.h: add rdtsc() inline. trace.c is NOT a separate file (ptable is
   anonymous): implement the ring in proc.c or a header-only helper called from
   proc.c. Per-CPU ring of TRACE_SIZE entries {uint tlo,thi; short cpu,pid,ev;
   int arg; uint seq;}, global seq counter, all writers hold ptable.lock
   (document this). Events SWITCH_IN/OUT (scheduler), DONATE/WITHDRAW/CYCLE
   (donation code), DEADLINE_MISS. Replace the Stage 5 event array with the ring
   while keeping the deferred-print debug mode.
2. Syscalls 26 schedtrace(struct trace_ent *dst, int max): clamp max to what
   the rings hold, argptr with max*sizeof(struct trace_ent), copy oldest-first
   per CPU, return the count; 27 tracectl(int cmd): 0 off, 1 on, 2 clear,
   3 print-donate-debug on, 4 off. struct trace_ent goes in sched_api.h.
3. user/schedtrace.c prints "tlo thi cpu pid ev arg seq" lines.
User:
4. Full wfgen.c as described in my plan (2..6 stages, only the last stage calls
   setworkflow, hygiene, single-write RESULT line, hogs created first,
   cleanup). Print "wfgen: workflow rejected by kernel" if setworkflow fails.
5. calib.c: busy loop N iterations, print tick delta.
Host:
6. host/plots/plot_gantt.py: parse schedtrace output text, one lane per CPU,
   a bar per pid interval, vertical markers for DONATE/WITHDRAW/CYCLE; PNG.
7. harness/run_all.py as in my plan (policies x cpus x 20 runs, restart per
   run with QEMUEXTRA=-snapshot, strict RESULT regex, CSV with columns
   policy,cpus,run,alpha,finish,deadline,miss,status,commit_hash,rawlog_path,
   resume support, --dry-run with 2 runs per cell, survive panic/timeout).
8. Update docs: DESIGN.md, PARAMS.md, SYSCALLS.md rows 26-27, TEST_TABLE.md
   rows T-46..T-53, LIMITATIONS.md, VIVA.md.
Do not change donation logic. Show how to run each tool.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-46 | `wfgen` unloaded | `miss=0`, finish about `W` |
| T-47 | `wfgen` with hogs under `rr`, tight deadline | likely `miss=1` |
| T-48 | pipes block | trace shows readers sleeping; `DONATE` events appear under `edf_donate` |
| T-49 | trace ring wraps | no crash after many events |
| T-50 | harness `--dry-run` | CSV rows for all 6 cells |
| T-51 *(negative)* | kill QEMU mid-run | harness records the failure row and continues |
| T-52 | re-run harness | skips finished rows |
| T-53 | interleaving check | `RESULT` lines never corrupted (parser strict) |

**Commit note.**

```
stage6: wfgen, trace ring, Gantt plot, unattended harness
Calibration: work=<N> -> W=<ticks> (mean of 5, sd <x>).
Failed: <bytes < PIPESIZE so no blocking / interleaved RESULT line / ring index bug>
Dry run OK; full run scheduled.
```

**Definition of done.** `tools/check_submission.sh 6` green.

---

### Stage 7 (Days 15–17): measurements and the closed-loop agent

**In plain words.**
Run the experiments and make the graphs. **Before looking at any data, write down what you expect**, commit it, then run. That is how you tell a real result from a bug. Expected story: round-robin shares the CPU with hogs, so the pipeline is slow and misses; EDF without donation also misses, because the urgent last stage is asleep and EDF only considers ready processes while stages 1–3 have no deadline; EDF with donation misses far less. Then show the agent using these observations to choose a better policy by itself.

**Technical details.**

*Experiment model.* Let `W` be the unloaded pipeline time and `h` the hog count. Under fair sharing the active stage gets about `1/(h+1)` of a CPU, so `T_RR ≈ (h+1)·W` on one CPU. With EDF plus donation `T ≈ W + overhead`. The informative deadline window is `W < D < (h+1)·W`; set `D = α·W` and sweep `α ∈ {1.2, 1.5, 2, 3}` (N8).

*Statistics.* Report misses out of 20 with a 95% bootstrap confidence interval (10 000 resamples, fixed seed), mean and median finish ticks, and Fisher's exact test comparing `edf` vs `edf_donate`. With `n = 20` the test has little power; say so. State that QEMU/TCG timing is nondeterministic.

*Closed-loop agent (N6).* An `AdaptivePlanner`: run a pilot with `rr` and the user's deadline; if `miss=1`, switch to `edf_donate`, rerun, compare; stop after 3 steps. Every step is an audit record. The decision rule is plain Python code over the parsed observation (not model text).

**Living documents to update.**

| File | What to write now |
|---|---|
| `docs/predictions.md` | Your predictions with dates, **committed before the full batch**. |
| `REPORT_NOTES.md` | *Results* (150 words plus the three best graphs), *Problems* (80 words), updated *Limits*. |
| `EVIDENCE_INDEX.md` | Every graph → CSV rows → raw log directory → commit hash. |
| `TEST_TABLE.md` | T-54..T-60. |
| `PARAMS.md` | Final `W`, `α`, hogs, bytes, commit hash. |
| `LIMITATIONS.md` | Small `n`, TCG noise, anomalies, any dropped runs. |
| `VIVA.md` | "Explain this graph" answers. |

**Manual steps (human only).**

1. Write and commit `docs/predictions.md` first.
2. Launch the full batch (overnight if needed): 3 policies × 2 CPU counts × 20 runs at the main `α`, then the sweep (10 runs per cell is acceptable if time is short, state it).
3. Inspect any odd run (a miss under donation, a panic). Do not delete outliers silently; log them in `LIMITATIONS.md`.
4. If results contradict the prediction, debug before plotting. Usual causes: pipes never block, hogs ≤ CPUs, deadline outside `(W, (h+1)W)`, tie-break not applied.
5. Choose the three graphs that fit in two handwritten pages.
6. Keep every raw log; zip them for the evidence bundle.

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 7: analysis and the adaptive agent. No kernel changes.

Input: results/results.csv with columns
policy,cpus,run,alpha,finish,deadline,miss,status,commit_hash,rawlog_path.
1. harness/analyze.py: drop rows with status != ok but report how many per
   cell; print and save results/summary.csv and results/summary.md with, per
   (policy,cpus[,alpha]): n, misses, miss rate, 95% bootstrap CI for the miss
   rate (10000 resamples, seed fixed), mean and median finish; Fisher exact
   test edf vs edf_donate per cpus (scipy if available, else manual) with a
   note that n is small.
2. host/plots/plot_results.py: misses_bar.png (3 policies x 2 cpu counts),
   miss_vs_alpha.png (lines with error bars), finish_box.png (boxplot with a
   horizontal line at the deadline).
3. host/planners/adaptive.py: AdaptivePlanner: pilot run under rr, if the
   parsed observation has miss=1 then set_policy edf_donate and rerun, compare,
   stop after at most 3 steps; decisions are plain code over parsed fields.
   Add --planner adaptive to agent.py and write each step to audit.jsonl.
4. docs/results_template.md filled automatically from summary.csv (tables only;
   leave the Explanation and Anomalies sections for me).
5. Update docs/EVIDENCE_INDEX.md with a generator script tools/index_evidence.py
   that lists every graph and the CSV/raw-log paths it came from, TEST_TABLE.md
   rows T-54..T-60 (Observed PENDING).
Never smooth, drop or alter data beyond the stated rules.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-54 | misses, 4-stage, `CPUS=1` | `rr` high, `edf` high, `edf_donate` clearly lower |
| T-55 | `CPUS=3` | pattern holds or weaker; explanation written |
| T-56 | miss rate vs α | `edf_donate` reaches near-zero at smaller α |
| T-57 | Gantt for `edf` | stages 1–3 starved while the hog runs |
| T-58 | Gantt for `edf_donate` | stages 1–3 run early, donation markers just before |
| T-59 | adaptive agent with a tight deadline | switches to `edf_donate` after a miss; audit shows both runs |
| T-60 | every graph has a registered raw-log source | `EVIDENCE_INDEX.md` complete |

**Commit note.**

```
stage7: full measurement batch, analysis, adaptive agent
Prediction (committed earlier): rr/edf high misses, edf_donate low.
Observed: rr <a>/20, edf <b>/20, edf_donate <c>/20 on CPUS=1 (alpha=<x>).
Anomalies: <list or none>. Raw logs: logs/run_<date>/.
```

**Definition of done.** `tools/check_submission.sh 7` green (requires `results/results.csv`).

---

### Stage 8 (Days 18–20): freeze, rehearse, package

**In plain words.**
No new features. Everything you need already exists in the living documents; this stage is a read-through, filling the last blanks, rehearsing the viva, and producing the zip. The viva asks you to change something live (for example, extend donation through `wait()` or change the tie-break), so practise that.

**Technical details.**

- *Freeze:* tag the final commit (`git tag final`), do not touch kernel code except for bugs.
- *Clean-room rerun:* fresh clone → `make clean && make` → `make qemu-nox` → `usertests` → agent demo → injection demo (including the manual shell bypass). Anything depending on your local state is a bug.
- *Viva drills* to practise with a timer (add them to `VIVA.md` with the files you would touch and a 3-line approach): donation through `wait()` (parent waits on child: the child is the "holder"); FIFO tie-break; move the cycle check earlier or later; add a counter to `sched_stats`; change `MIN_SLACK` and show rejection; cap donation depth at K; add a new trace event; make the validator clamp instead of reject.
- *The report:* handwritten, strictly two pages. Copy from `REPORT_NOTES.md` (already sized by word budget). Include the donation-chain diagram, the best graphs, `effective(p)`, the wraparound-safe compare, `T_RR ≈ (h+1)W`, the recompute termination argument, and the cycle bound.

**Living documents to update (final pass).**

| File | Final action |
|---|---|
| `TEST_TABLE.md` | No `PENDING` left. Negative and benign controls present for each feature. |
| `EVIDENCE_INDEX.md` | Every row points to a file that exists. |
| `LIMITATIONS.md` | Final read; each item phrased "what the model leaves out compared with a full implementation". |
| `CONTRIBUTIONS.md` | Per-person highlights: files, functions, tests, plus `git shortlog -sn`. |
| `VIVA.md` | Drills complete; each member can answer the "validator vs kernel" question. |
| `JOURNAL.md` | Final entry; commit history shows a note every 2 days. |

**Manual steps (human only).**

1. Hand-copy the report (two pages exactly).
2. Everyone writes 3 to 4 lines about their own part into `CONTRIBUTIONS.md`.
3. Run `tools/check_submission.sh 8` and open the produced zip; verify it contains only added/modified files.
4. Run each viva drill once, timed (aim under 10 minutes each).
5. Ask the instructor whether raw logs and graphs go inside the zip or in a separate evidence bundle (see section 10).

**Agent prompt.**

````text
[Paste the master context prompt first.]

Stage 8: packaging and viva preparation. Do not change functionality.

1. Extend tools/check_submission.sh 8: fail on any PENDING or TODO anywhere in
   docs/, on EVIDENCE_INDEX rows pointing to missing files, on missing
   per-person entries in CONTRIBUTIONS.md, and if dist/Team_Name_3.zip
   contains build outputs. Print a final summary table.
2. docs/VIVA.md: complete it with a one-page cheat sheet (effective(); two
   fields; dl_before wraparound; tie-break; waiting_pipe plus fd scan; lock
   order table and the cprintf-under-ptable.lock deadlock; recompute
   termination; cycle handling; admission control and firm deadlines; why the
   validator is not the security boundary; limitations). Cite file:function
   for every statement, based only on the actual code.
3. Add 8 viva drills (donation through wait(); FIFO tie-break; moving the
   cycle check; a new sched_stats counter; changing MIN_SLACK; donation depth
   cap K; a new trace event; validator clamp vs reject) with the files to touch
   and a 3-line approach each.
4. Cross-check docs/TEST_TABLE.md against host/tests and user/ test programs and
   list tests that exist in code but not in the table and vice versa.
Do not invent results; leave unknowns as PENDING for me.
````

**Test.**

| ID | Test | Expected |
|---|---|---|
| T-61 | clean clone, full build and demos | works from scratch |
| T-62 | injection demo end to end | validator blocks; shell bypass blocked by kernel; benign control passes |
| T-63 | `usertests` under all three policies | pass |
| T-64 | zip contents | only added/modified files; per-person highlights present |
| T-65 | timed viva drills | each completed |

**Commit note.**

```
stage8: freeze, final docs pass, packaging, viva drills
Final: usertests pass on rr/edf/edf_donate; injection demo reproducible.
Known limits: docs/LIMITATIONS.md.
```

**Definition of done.** `tools/check_submission.sh 8` is green and `git tag final` exists.

---

## 10. What to submit (the manifest)

Everything below already exists in the repo because the living documents were maintained from Stage 0. Submission is `tools/make_zip.sh baseline` plus the handwritten report.

**A. `Team_Name_3.zip`** (naming: `Team_Name_problem_no`; contains **only files added or modified** relative to the `baseline` tag, with per-person highlights):

| Group | Contents |
|---|---|
| Kernel (xv6-public) | modified `proc.c proc.h pipe.c defs.h syscall.c syscall.h sysproc.c usys.S user.h param.h x86.h Makefile`, new `sched_params.h sched_api.h` |
| Guest programs | `xrun.c wfgen.c schedctl.c schedstat.c schedtrace.c edftest.c donatetest.c donate5.c cycletest.c killtest.c calib.c ticktest.c hello_test.c`, `report.txt`, `inbox.txt` |
| Host | `host/` (bridge, tools, validator, planners incl. deterministic/ollama/adaptive, audit, loop, agent, config.json, tests, demos, plots), `harness/` |
| Documents | `docs/` (design, test table, limitations, evidence index, syscalls, params, journal, viva, contributions, predictions, `gdb/`) |
| Per-person highlights | `docs/CONTRIBUTIONS.md` (who did which files/functions/tests) and `// Author: Pn` headers |

**B. Evidence** (graphs must come with the raw QEMU logs that produced them): `logs/` (raw per-run transcripts, `audit.jsonl`), `results/` (CSVs, graphs, Gantt charts), `docs/gdb/` (real GDB session). *Confirm with the instructor whether this goes inside the zip or as a separate bundle `Team_Name_3_evidence.zip`; the zip rule says "only files added or modified for the implementation", so default to a separate bundle if unsure.*

**C. The handwritten 2-page report** (strictly two pages): copied from `docs/REPORT_NOTES.md`.

**D. At the viva:** a laptop with the repo at tag `final`, QEMU built, the injection demo ready, and every member ready for a live modification.

---

## 11. Evaluation criteria mapped to what you do

| Rubric item | Where you satisfy it |
|---|---|
| Per-team parameters | `sched_params.h` + `config.json`, never hard-coded (Stage 0, `PARAMS.md`) |
| Hidden tests (5-stage chain + hog, pipe cycle, donor exits) | Stage 5 tests T-36, T-38, T-39 and harness (Stage 6) |
| Own run evidence | Raw logs per run; real GDB session (Stage 5); `EVIDENCE_INDEX.md` |
| Live viva change | `VIVA.md` drills (Stage 8, grown since Stage 2) |
| Design journal (note every 2 days) | `JOURNAL.md` and a commit note at every stage end |
| Documented limits | `LIMITATIONS.md`, appended the day each limit is found |
| Agent guide: tools, bridge, structured calls, injection test, kernel refusal, test table, logs | Stages 3, 4 and `TEST_TABLE.md` (positive, negative and benign controls) |
| Zip, per-person highlights, 2-page handwritten report | Section 10 |

---

## 12. Common ways this project fails

1. Starting donation before EDF is tested.
2. A workload that never blocks a reader (below `PIPESIZE`) or has no more hogs than CPUs.
3. Giving every stage the deadline.
4. **`cprintf` while holding `ptable.lock`:** deadlocks against the console interrupt (`cons.lock → ptable.lock`). Print after releasing.
5. **Taking `tickslock` under `ptable.lock`:** inverse of the clock interrupt's order.
6. Leaving a stale `waiting_pipe` after waking, killing or exiting.
7. Pipe ends not closed in `wfgen` (extra holders, no EOF, over-donation).
8. Trusting the validator alone. Always include the manual shell-bypass test.
9. Any compiler warning: `-Werror` stops the build (unused variables, missing prototypes).
10. Forgetting `make clean` after changing `param.h` or `fs` layout; the old `fs.img` stays tiny.
11. Overlong shell lines (the xv6 shell reads only 99 characters).
12. Interleaved console output from concurrent processes breaking your parser.
13. Pasting agent code without reading it: agents release locks early, forget early-return paths and invent functions that do not exist in this tree.
14. Leaving documentation for the end: a `PENDING` in `TEST_TABLE.md` at Stage 8 means an untested claim.
15. Fabricating a GDB log or hiding a limitation. Both cost more than the honest version.