# Journal

| Date | Stage | Entry |
| 2026-10-23 | 0 | Learned that `scheduler()` acquires `ptable.lock` before scanning for runnable processes and keeps it held across `swtch()`; the running process must release and reacquire it before returning to the scheduler. `sleep(chan, lk)` atomically transitions the process to `SLEEPING` while coordinating through `ptable.lock`, and `wakeup()` marks matching sleepers runnable. Pipe readers sleep on `&p->nread`, writers sleep on `&p->nwrite`, and the opposite operation wakes them. The LAPIC timer is programmed with an initial count of 10000000, but the source does not establish a wall-clock tick period. Only CPU 0 increments the global `ticks` value. |
| 2026-10-23 | 0 | Initially cited incorrect line numbers for the timer and tick descriptions in `DESIGN.md`; corrected them by checking the numbered source files. The submission checker also cannot package the project until the required `baseline` git tag is created. |
