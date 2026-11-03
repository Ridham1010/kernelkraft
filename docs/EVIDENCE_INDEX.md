# Evidence index

| Evidence file | Test or claim | Description |
|---|---|---|
| `logs/20261023-163147.raw` | T-02 | Raw serial-console log produced by `QemuBridge` while running `ls`. |
| `logs/20261023-163207.raw` | T-03 and T-04 | Raw serial-console log produced by `QemuBridge` while running `usertests`; the tick capture is in `logs/T-03-ticktest.raw`. |
| `logs/T-01-hello.raw` | T-01 | Captured `hello_test` output. |
| `logs/T-02-ping.out` | T-02 | Host-side printed `ls` result, including `README`, `hello_test`, and `ticktest`. |
| `logs/T-03-ticktest.raw` | T-03 | Tick output and stopwatch measurement. |
| `logs/T-04-usertests.raw` | T-04 | Post-`FSSIZE` usertests output containing `ALL TESTS PASSED`. |
| `Unavailable: logs/20261025-211404.raw` | T-06, T-11, T-12 | Historical Stage 2 observations remain recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `Unavailable: logs/20261025-212038.raw` | T-07 | Historical Stage 2 observation remains recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `Unavailable: logs/20261025-211715.raw` | T-08 | Historical Stage 2 observation remains recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `Unavailable: logs/20261025-211536.raw` | T-09 | Historical Stage 2 observation remains recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `Unavailable: logs/20261025-211846.raw` | T-10 | Historical Stage 2 observation remains recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `Unavailable: logs/20261025-212854.raw` | T-13 | Historical Stage 2 observation remains recorded in `TEST_TABLE.md`, but this raw log is not present in the current checkout. |
| `logs/20261026-022527.raw` | T-05 | Temporary real-QEMU negative run after removing only `_hello_test`: `hello_test` was unavailable, but xv6 printed `exec: fail` and `exec hello_test failed`, not the specified literal `hello_test: not found`; `ls` also omitted `hello_test`. |
| `logs/20261026-022603.raw` | T-05 restoration check | Real-QEMU run after restoring the exact Makefile and rebuilding: `hello_test` printed `hello from kernel` and `hello() returned 0`. |
| `logs/audit.jsonl` records 1-3 | T-15 through T-21 | Fake-bridge smoke records from the earlier host-loop test; these are not QEMU evidence. |
| `logs/audit.jsonl` records 4-5 | Earlier T-14 attempt | Earlier real-QEMU attempt where `cat /report.txt` completed with `cat: cannot open /report.txt`; not the successful T-14 evidence. |
| `logs/20261026-014457.raw` | Earlier T-14 attempt | Earlier real serial-console transcript showing the missing-file attempt; not the successful T-14 evidence. |
| `logs/audit.jsonl` records 6-7 | T-14 | Real-QEMU audit records: `ls` output includes `report.txt`, and `read_file` output contains all three report lines. |
| `logs/20261026-020550.raw` | T-14 | Successful real serial-console transcript showing the listing, the three `report.txt` contents, and matching `@@DONE` sentinels. |
| `logs/20261026-021004.raw` | T-23 | Real QEMU run: nonexistent `stage3_missing_program` produced `@@EXECFAIL` followed by `@@DONE`; a subsequent `ls` completed with `@@DONE` and returned `README`. |
| `logs/20261026-021019.raw` | T-22 | Real QEMU run: `xrun ... cat` blocked on console input until the one-second bridge timeout; the session was terminated during restart. |
| `logs/20261026-021021.raw` | T-22 | Fresh QEMU session after timeout recovery; `ls` completed with `@@DONE` and returned `README`. |
| `host/tests/test_validator.py` | T-15 through T-21 and T-24 | Pytest coverage for unknown-tool rejection before bridge calls, invalid paths and allowlist, deadline and hog bounds, malformed arguments, bool-as-int rejection, per-run logging, CPU-preserving restart, and the full 17-test suite. |
| `docs/gdb/stage5-session.txt` | Manual step 6 | Real GDB session connected to QEMU on port 26000, broke in `scheduler`, recorded a backtrace and CPU thread, then detached. |
| `logs/20261026-220615.raw` | T-25 and T-28 | Stage 4 benign agent/manual workflow output with a successful `RESULT` line. |
| `logs/audit.jsonl` latest records | T-26 | Injected `/inbox.txt` scenario: the proposed deadline-1 pipeline was rejected by the host validator before guest execution. |
| `logs/T-27-stage4.raw` | T-27 | Manual shell bypass capture showing `admit: rejected ... reason=slack` and `wfgen: workflow rejected by kernel`. |
| console captures from Stage 4 runs | T-30 through T-32 | Overdue workflow reported `miss=1`; fresh-filesystem usertests passed under all three policies; CPUS=3 workflow completed without panic. |
| `logs/T34-T41-cpus1.raw` | T-34, T-35, T-38, T-39, T-40 | CPUS=1 EDF baseline, donation chain, five-stage chain, cycle, corrected two-donor withdrawal, and regression run capture. |
| `logs/T36-T40-cpus3.raw` | T-36, T-38, T-40, T-42 | CPUS=3 five-stage chain, cycle, withdrawal, and no-panic chain capture. |
| `logs/T38-T40-final-cpus1.raw` | T-38 through T-40 | Final CPUS=1 cycle and two-donor withdrawal capture after the sentinel and test-topology fixes. |
| `logs/T38-T40-final-cpus3.raw` | T-38 through T-40 | Final CPUS=3 cycle and two-donor withdrawal capture. |
| `logs/T39-T40-kill-cpus1.raw` | T-39, T-40 | Final CPUS=1 kill test: finite donation after one donor and `FFFFFFFF` after both donors. |
| `logs/T39-T40-kill-cpus3.raw` | T-39, T-40 | Final CPUS=3 kill test: finite donation after one donor and `FFFFFFFF` after both donors. |
| `logs/T41-usertests-cpus1.raw` | T-41 | Fresh-filesystem CPUS=1 `usertests` under `edf_donate`, ending `ALL TESTS PASSED`. |
| `logs/T41-usertests-cpus3.raw` | T-41 | Fresh-filesystem CPUS=3 `usertests` under `edf_donate`, ending `ALL TESTS PASSED`. |
| `logs/T43-negative-rr.raw` | T-43 | RR negative run: zero donations and no `donate:` diagnostics. |
| `logs/T43-negative-edf.raw` | T-43 | EDF negative run: zero donations and no `donate:` diagnostics. |
| `logs/T44-smallpipe.raw` | T-44 | Sub-512-byte pipe sanity run completed with `RESULT smallpipe` and no donation output. |
| `logs/T45-stress20.raw` | T-45 | Twenty consecutive donation-test runs completed with no panic or hang. |


| `logs/stage6-calibration/` | T-46/manual step 1 | Five CPUS=1 zero-hog calibration logs; finishes 14, 13, 13, 14, 14 ticks, mean 13.6, SD 0.55. |
| `results.csv` | T-50 | Clean dry-run CSV with 12 rows; CPUS=1 succeeds and CPUS=3 is blocked by guest CPU detection. |
| `logs/T49-trace-wrap.raw` | T-49 | 70 workloads followed by `schedtrace 256`; no panic and 256 retained entries. |
| `logs/T51-kill-midrun.raw` | T-51 | Harness timeout classification and raw log after forced termination. |
| `logs/T52-resume.raw` | T-52 | Resume run skipped all 12 completed keys. |
| `logs/T53-interleave.raw` | T-53 | Concurrent second workflow rejected by admission; accepted RESULT remained intact. |
| `host/plots/gantt-edf-donate.png` | Visual/manual step 4 | Gantt chart generated from 200 trace entries containing donation markers. |