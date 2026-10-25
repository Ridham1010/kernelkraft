# xv6 Projects: Operating Systems Lab (CSL3030)
**Indian Institute of Technology Jodhpur**

* **Team:** 3 to 4 students
* **Duration:** 15 to 20 days
* **Scope:** One problem per team

## 1. Introductory Instructions

Every one of these projects lives at the same place in the stack. An agent decides to do something, a user-space program carries it out, and the action arrives at the kernel as an ordinary system call. The kernel is the last component that sees the action and the only one that can refuse it.

### Before You Begin
* **Kernel:** xv6-riscv. Note four differences from older tutorials: `sleep()` is split into a prepare step followed by the sleep itself; the kernel print is `printk()`, not `cprintf()`; the log constants are `LOGBLOCKS` (30) and `MAXOPBLOCKS` (10); and `copyin`/`copyout` take the process size. Always check the real prototype in `kernel/defs.h` before calling a kernel function.
* **Files to read first:** `syscall.c`, `syscall.h`, `sysproc.c`, `sysfile.c`, `user/user.h`, `user/usys.pl`, `proc.c`, `proc.h`, `trap.c`, `defs.h`, `param.h`. Reading comes first: days 1 to 3 of the timeline are for reading, not coding.
* **Build and run:** `make qemu` to boot, `make CPUS=1 qemu` while debugging, `make CPUS=3 qemu` to expose races. Quit QEMU with Ctrl-A then X.
* **Changing fs.h:** If you change `fs.h` or `mkfs/mkfs.c`, run `make clean && make qemu`, without exception.
* **Checkpoints:**
    * Day 4: Worked example running (see original PDF).
    * Day 10: Core mechanism working for one process at CPUS=1, happy case only.
    * Day 14: Your test harness running unattended. Cut scope at day 10 if behind.

### Kernel Patterns You Will Need
1. **Spinlocks:** Protects shared data. `initlock(&lk, "mylock");`, `acquire(&lk);`, `release(&lk);`. Never sleep while holding a spinlock.
2. **Sleeping and Waking:** A process that must wait sleeps on a "channel". Always re-check the condition in a `while` loop, never an `if`.
3. **Reading the Clock:** `ticks` is a global counter. Sleep on `&ticks` to wait for time to pass. Use `uint` to calculate elapsed time to handle wrap-arounds correctly.
4. **Disk Transactions:** Wrap related disk writes in `begin_op();` and `end_op();`.

---

## 2. Project Instructions: 3. Deadline scheduler with priority donation through pipes (Medium)

**Question:** Replace the xv6 round-robin scheduler with a workflow-aware Earliest Deadline First (EDF) scheduler in which a process waiting on a pipe lends its urgency to the process that will fill that pipe.

**Explanation:** An agent workflow is a chain of steps, often connected by pipes, that must finish before a deadline. If an urgent step waits for a slow helper that the scheduler treats as unimportant, the whole workflow misses its deadline (priority inversion). xv6 records only the address a sleeper is waiting on, never which process is expected to wake it. Adding that one pointer is what makes the whole problem solvable.

### What to be done:
1. Add `setworkflow(wid, deadline_ticks)`. Processes in one workflow share its deadline. Processes with no workflow get a deadline of infinity. Keep the donated deadline in a field of its own, separate from the process's own deadline, so it can be withdrawn later.
2. Change `scheduler()` in `proc.c` to always run the runnable process with the earliest effective deadline, where the effective deadline is the earlier of its own and any donated one.
3. Record the writer side of each pipe in `struct pipe`. When a reader sleeps on an empty pipe, the writer gets the reader's deadline if it is earlier.
4. Make donation chain through at least 4 stages and detect cycles so the kernel does not loop forever.
5. Remove donated priority when the pipe gets data, when the reader exits, or when the donor is killed.
6. Build a workload generator that starts pipelines with chosen lengths, CPU work per stage and deadlines.

**Files to modify:** `proc.c`, `proc.h`, `pipe.c`, `sysproc.c`, `syscall.c`, `syscall.h`, `defs.h`, `user/`, `Makefile`.

### Hints:
* Get EDF working and tested before you start donation. Debugging both at once is what sinks this project.
* `PIPESIZE` is 512 bytes: if your stages push less than that the reader never blocks, nothing is ever donated, and your experiment measures nothing.
* If two readers donated to one writer, removing one donation should restore the other, not clear the field. Either keep a list of donors, or recompute by scanning for any process whose `waiting_on` points here. Pick one and say why.

### Expected Output:
* A table and graph of deadline misses for round-robin, EDF without donation and EDF with donation, on 1 CPU and 3 CPUs, for 20 runs each.
* EDF with donation must show fewer misses on the 4-stage pipeline test.
* A kernel print mode shows each donation event as donor pid, receiver pid and new deadline.
* Round-robin should miss often; EDF without donation should also miss often; EDF with donation should be clearly better.

### Hidden Tests:
A 5-stage chain with an unrelated CPU hog, a pipe cycle between two processes, and a donor that exits while donation is active.

### Code to start from

**`kernel/proc.h`**
```c
struct proc {
  // existing fields
  int wid;                   // workflow id, 0 = none
  uint deadline;             // its own: NO_DEADLINE = none
  uint donated;              // lent by a waiter; NO_DEADLINE = none
  struct proc *waiting_on;   // who must run before we can
};

#define NO_DEADLINE 0xffffffff

static uint
effective(struct proc *p)
{
  return p->donated < p->deadline ? p->donated : p->deadline;
}
```

**`kernel/proc.c` - the EDF scan**
```c
struct proc *best = 0;
for(struct proc *p = proc; p < &proc[NPROC]; p++){
  acquire(&p->lock);
  // < and not <=: with <, ties always go to the lowest index in
  // proc[], and a process at a high index can starve forever.
  if(p->state == RUNNABLE && (best == 0 || effective(p) < effective(best))) {
    if(best)
      release(&best->lock);
    best = p;
  } else {
    // keep best->lock HELD and carry on
    release(&p->lock);
  }
}

if(best) {
  // We still hold best->lock, so it cannot have exited or slept
  // since we chose it. Releasing every lock during the scan and
  // re-acquiring the winner's afterwards is the classic bug here.
  best->state = RUNNING;
  c->proc = best;
  swtch(&c->context, &best->context);
  c->proc = 0;
  release(&best->lock);
}
```

**`kernel/proc.c` - donation along the chain**
```c
void
donate(struct proc *to, uint dl)
{
  int depth = 0;
  // Two processes can genuinely block on each other's pipes, making
  // this chain a cycle. Without the bound the kernel spins here with
  // interrupts off and the machine hangs unrecoverably.
  while(to != 0 && depth++ < NPROC) {
    if(to->donated <= dl)
      break;                     // already at least this urgent: stop
    to->donated = dl;
    to = to->waiting_on;         // follow the chain backwards
  }
}
```

**`kernel/pipe.c` - recording the dependency**
```c
// in piperead(), where the reader finds the pipe empty:
while(pi->nread == pi->nwrite && pi->writeopen) {
  struct proc *p = myproc();
  p->waiting_on = pi->writer;    // who we are waiting for
  if(pi->writer)
    donate(pi->writer, effective(p)); // lend our urgency

  sleep_prepare(&pi->nread);
  release(&pi->lock);
  sleep();
  acquire(&pi->lock);
}
myproc()->waiting_on = 0;        // and undo it on the way out
```

---

## 3. Evaluation Rules, Timeline and Deliverables

### Evaluation Rules
No project is fully LLM-proof, so these rules carry as much weight as the problems themselves.
* **Per-team parameters:** Each team gets its own cost table, deadline formula or conflict rule. A generic answer fails hidden tests. Read parameters from an easy-to-change place.
* **Hidden tests:** You get about 30% of the tests. The crash, race and laundering tests stay with the instructor.
* **Own run evidence:** Graphs must come with raw QEMU logs. One GDB session log showing a real bug you found and fixed is required.
* **Live viva change:** In the viva, teams make a small change on the spot.
* **Design journal:** A git commit with a short note every 2 days on what failed and why. One huge final commit is a red flag.
* **Documented limits:** A limitation you found and wrote down scores above one you concealed.

### Timeline
* **Days 1 to 3:** Read the problem statement and the relevant xv6 files
* **Days 4 to 10:** Build the core mechanism
* **Days 11 to 14:** Write tests and the crash or race harness
* **Days 15 to 17:** Run measurements and make graphs
* **Days 18 to 20:** Write the report and prepare for the viva

### Deliverables
1. The zip file, named `Team_Name_problem_no`, containing **only** the files that are added or modified for the implementation. Per person on the team, highlighting their part of the work.
2. A handwritten report of 2 pages, per team, explaining how you solved the problem and the problems encountered, well explained with mathematical expressions if required. Strictly 2 pages.