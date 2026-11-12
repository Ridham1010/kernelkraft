# Contributions

Team KernelKraft, CSL3030 Operating Systems Lab, IIT Jodhpur.

## Atharv Dhuvad (B24CS1085) - [@centauri1219](https://github.com/centauri1219)

**Project setup.** Imported the xv6 source tree and laid out the repository:
the documentation skeleton, the host-side directory, the shared parameter
header and the packaging and submission-check scripts. Ran the stock
`usertests` suite on the untouched tree to establish a baseline before any
kernel change.

**First system call and serial bridge.** Added the `hello` system call end to
end (`syscall.h`, `user.h`, `usys.S`, `syscall.c`, `sysproc.c`) with its test
program, and wrote the first version of the QEMU serial-console bridge that
the host agent later builds on. Raised the filesystem size from 1000 to 4000
blocks so the extra user programs fit, and measured the tick rate of the
emulated machine with `ticktest`.

**Admission control and firm deadlines.** Implemented the kernel-side
admission check in `setworkflow`, which refuses a workflow whose deadline is
too close to be met and caps the number of urgent processes, together with the
per-workflow and global rejection counters. Implemented firm deadlines: a
process that has missed its deadline is marked and no longer competes as
urgent work. Wrote the first working version of the workload generator
`wfgen`.

**Injection demonstration.** Connected the host agent to the kernel and built
the injected-instruction demo. A hostile request hidden in a file asks for a
1-tick deadline with 8 hogs; the host validator blocks it, and the same
command typed directly at the xv6 shell is refused by the kernel.

**Priority donation through pipes.** Implemented the core mechanism of the
project in `proc.c` and `pipe.c`:

- the wait hooks in `piperead` that record which pipe a process is asleep on;
- the scan of file-descriptor tables that finds the processes holding a
  pipe's write end;
- the iterative depth-first donation walk with an explicit stack, which
  carries a deadline back through a chain of pipes and detects cycles;
- withdrawal by clearing and recomputing all donations to a fixed point when
  a reader wakes, exits or is killed;
- deferring kernel printing until `ptable.lock` is released, so that the
  donation print mode cannot deadlock against the console.

Added the `procinfo` and `tracectl` system calls and the donation test
programs `donatetest`, `donate5`, `cycletest`, `killtest` and `smallpipe`, and
ran them on one and three CPUs along with a 20-run stress test.

**Report.** Edited the final project report.

## Ridham Shah (B24CS1064) - [@Ridham1010](https://github.com/Ridham1010)

**EDF scheduler.** Replaced the round-robin loop in `scheduler()` with a
policy that can be switched at run time between round-robin, EDF and EDF with
donation. Implemented the selection of the runnable process with the earliest
effective deadline and the least-recently-run tie-break, which keeps processes
without deadlines from starving one another.

**Workflows.** Added the workflow table and the deadline fields in
`struct proc`, inheritance of the deadline across `fork`, and release of the
workflow on `exit`. Added the system calls `setsched`, `setworkflow` and
`schedinfo`, the shared header `sched_api.h`, and the user programs
`schedctl`, `schedstat`, `edftest` and `test_negative`.

**Scheduler tracing.** Built the per-CPU trace ring in the kernel, which
records switch-in, switch-out, donation, withdrawal, cycle and deadline-miss
events with `rdtsc` timestamps, the `schedtrace` system call and program that
export it, and the `tracectl` program that controls it. Wrote the Gantt-chart plotter that turns a trace into a
picture of which process ran when.

**Workload and measurement tooling.** Extended the workload generator `wfgen`
to build pipelines of 2 to 6 stages beside a chosen number of CPU hogs and to
print a machine-readable `RESULT` line. Wrote `calib` and ran the first
calibration of the unloaded pipeline. Wrote the first version of the
unattended harness that boots QEMU from a snapshot for every run, and which
can resume an interrupted batch.

**Submission.** Carried out the freeze and the final documentation pass,
wrote the viva questions and change drills, and extended the submission
checker to verify documentation placeholders, evidence paths, contributor
entries and the absence of build outputs in the archive.

## Pranav H Nair (B24CS1056) - [@pranav-codee](https://github.com/pranav-codee)

**Host agent.** Built the host side of the project:

- the bridge protocol, in which each command sent to xv6 is wrapped by the
  `xrun` program with a random nonce so that echoed input cannot fake
  completion, with recovery from timeouts and failed `exec`;
- the tool registry and the validator that checks tool names, argument types,
  ranges and the file allowlist before anything reaches xv6;
- the deterministic planner, the agent loop and the audit log;
- the test suite for the validator and bridge.

**Scheduler bug.** Found and fixed the ordering bug in `dl_before`: the
"no deadline" sentinel behaved as the earliest possible deadline under the
wrap-safe comparison, so EDF and EDF with donation both finished late in the
pilot runs.

**Measurements and analysis.** Rewrote the harness to sweep policies, CPU
counts and deadline multipliers and to record the kernel commit and raw log
for every row. Wrote the analysis (miss counts, bootstrap confidence
intervals, Fisher's exact test) and the result plots. Calibrated the unloaded
completion time, committed predictions before each batch, and ran the
measurement batches. Found that the first batch did not block the pipeline
stages enough to exercise donation, set it aside and reran it. Found why xv6
started only one CPU under QEMU's default machine type and which machine type
fixes it.

**Adaptive planner.** Wrote the planner that runs a workload under
round-robin, switches to EDF with donation if the deadline is missed, and
compares the two outcomes, with its tests.

**Final kernel fixes.** Made the last round of changes to the kernel:

- the kernel boots in EDF with donation;
- a process that calls `setworkflow` later joins the existing workflow and
  shares its deadline;
- a refused admission no longer leaves its table slot allocated, confirmed
  before and after in GDB;
- `fork` counts the child as a workflow member;
- `struct pipe` records its writer, which alone receives the donation once it
  has written;
- `fork` donates to a child that inherits a write end an urgent reader is
  already asleep on, which fixed cycle detection on three CPUs.

Rewrote the donation tests so that only the urgent process holds a deadline,
added `wftest`, ran the final 480-run batch, and wrote the report with the
team.
