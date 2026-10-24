# Limitations

| ID | Limitation | Impact | Workaround |
|---|---|---|---|
| L-01 | Global `ptable.lock` is coarse-grained | Limits scalability on multi-core; fine for NCPU ≤ 8 | N/A for course scope |
| L-02 | One `setworkflow` per process | Process cannot change workflow after joining | Design choice; workflows are immutable per process |
| L-03 | Workflow table size fixed at NWF=8 | Maximum 7 concurrent workflows (0 is reserved) | Increase NWF in `sched_params.h` if needed |
| L-04 | No deadline miss detection in Stage 2 | `misses` counter stays at 0 | Will be implemented in Stage 3 with timer-based checking |
| L-05 | Priority donation not implemented yet | `edf_donate` policy behaves same as `edf` | Stage 3 will implement donation through pipes |
| L-06 | No admission control beyond basic checks | `admission_check_locked` is a stub | Stage 3 will implement admission based on utilization |
| L-07 | `last_run` counter can wrap | 32-bit counter wraps after 4B scheduling cycles | Negligible for practical runs |
| L-08 | `ticks` wrap-around handled only in `dl_before` | Other comparisons of deadlines may be incorrect if not using `dl_before` | Always use `dl_before` for deadline comparisons |

