# Limitations

| ID | Limitation | Impact | Workaround |
|---|---|---|---|
| L-01 | Global `ptable.lock` is coarse-grained | Limits scalability on multi-core; fine for NCPU ≤ 8 | N/A for course scope |
| L-02 | One `setworkflow` per process | Process cannot change workflow after joining | Design choice; workflows are immutable per process |
| L-03 | Workflow table size fixed at NWF=8 | Maximum 7 concurrent workflows (0 is reserved) | Increase NWF in `sched_params.h` if needed |
| L-04 | Deadline miss detection is sampled at scheduler/exit boundaries | A process that remains outside those paths is marked on the next scheduler scan | Use scheduler and exit observations as the firm-deadline measurement points |
| L-05 | Donation uses an over-approximate holder scan and a benign race on `ofile` | A process can temporarily receive donation while it still has a duplicated writable descriptor | Donation is limited to pipes; close unused descriptors in tests |
| L-17 | Donation is only modeled through pipes, not `wait`, locks, or regular files | Other priority-inversion paths are not accelerated | Use explicit pipe pipelines for this stage |
| L-18 | Each donation event scans `NPROC * NOFILE` descriptor entries | Cost grows with the fixed process and descriptor-table sizes | Keep `NPROC` and pipe fan-out bounded |
| L-06 | Admission control uses the configured slack and global urgent-process cap | It is not utilization-based admission control | Tune `MIN_SLACK` and `MAX_URGENT` in `sched_params.h` |
| L-07 | `last_run` counter can wrap | 32-bit counter wraps after 4B scheduling cycles | Negligible for practical runs |
| L-08 | `ticks` wrap-around handled only in `dl_before` | Other comparisons of deadlines may be incorrect if not using `dl_before` | Always use `dl_before` for deadline comparisons |
| L-09 | xv6 has no process exit status | The bridge can report sentinel completion or exec failure, but not child return codes | Emit explicit result text from guest tools |
| L-10 | xv6 shell input is limited to 99 characters | Long guest commands cannot be sent safely | Fixed templates and a command limit below 90 characters |
| L-11 | Serial/QEMU timing is approximate | Timeout and deadline observations vary with host load | Record raw logs and repeat measurements |
| L-12 | Concurrent user output can interleave character writes | A line from multiple processes may not be readable as one record | Guest tools should construct important lines before one write |
| L-13 | `@@DONE` reports process completion, not command semantics | xv6 has no exit status, so a command such as missing-file `cat` needs host-side output classification | Record both observation status and raw guest output |
| L-14 | Fork-inherited deadlines | A fork child inherits its parent's own deadline | Admission counts each live finite-deadline process; callers must account for inherited urgency |
| L-15 | `MAX_URGENT` is global | The cap is shared by all processes, not isolated per user | Treat it as a kernel-wide safety limit |
| L-16 | Firm deadlines hide late work from EDF | A missed process is changed to `NO_DEADLINE` and becomes best-effort | Miss counters and raw logs retain evidence of lateness |
