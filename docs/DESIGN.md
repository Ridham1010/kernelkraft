# Design

## Reading notes

- **Scheduler and switching:** `scheduler()` enables interrupts, acquires
  `ptable.lock`, scans for `RUNNABLE` processes, and calls `swtch()` to the
  selected process. The process must release and reacquire `ptable.lock`
  before switching back; the scheduler releases it after the scan
  ([xv6-public/proc.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/proc.c):320-354).
- **Sleep and wakeup:** `sleep(chan, lk)` acquires `ptable.lock` before
  releasing a different lock, marks the caller `SLEEPING`, enters `sched()`,
  then reacquires the original lock after wakeup. `wakeup1()` changes matching
  sleepers to `RUNNABLE` while `ptable.lock` is held; `wakeup()` supplies that
  lock ([xv6-public/proc.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/proc.c):406-450).
- **Pipe blocking:** `pipewrite()` waits while the ring is full by sleeping on
  `&p->nwrite`; `piperead()` waits while empty and open by sleeping on
  `&p->nread`. Readers wake writers after consuming data, writers wake readers
  after producing data, and `pipeclose()` wakes the opposite side on close
  ([xv6-public/pipe.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/pipe.c):57-111).
- **Timer and ticks:** `lapicinit()` programs each local APIC timer in periodic
  mode with initial count `10000000` ([xv6-public/lapic.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/lapic.c):55-73).
  The timer trap increments `ticks` and wakes its waiters only when
  `cpuid() == 0`, preventing multiple CPUs from counting the same clock
  ([xv6-public/trap.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/trap.c):49-57).
- **Shell pipelines:** `runcmd()` creates one pipe, forks the left child and
  maps its stdout to the pipe write end, then forks the right child and maps
  its stdin to the pipe read end. Each child closes both unused descriptors;
  the shell parent closes both descriptors and waits for both children
  ([xv6-public/sh.c](/home/atharv/Documents/OS/kernelkraft/xv6-public/sh.c):86-116).

## Stage 0 scope

This stage records the existing design only. No kernel scheduling or pipe
logic is changed.
