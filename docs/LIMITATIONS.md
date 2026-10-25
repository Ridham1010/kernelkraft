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
| L-09 | xv6 has no process exit status | The bridge can report sentinel completion or exec failure, but not child return codes | Emit explicit result text from guest tools |
| L-10 | xv6 shell input is limited to 99 characters | Long guest commands cannot be sent safely | Fixed templates and a command limit below 90 characters |
| L-11 | Serial/QEMU timing is approximate | Timeout and deadline observations vary with host load | Record raw logs and repeat measurements |
| L-12 | Concurrent user output can interleave character writes | A line from multiple processes may not be readable as one record | Guest tools should construct important lines before one write |
| L-13 | `@@DONE` reports process completion, not command semantics | xv6 has no exit status, so a command such as missing-file `cat` needs host-side output classification | Record both observation status and raw guest output |

