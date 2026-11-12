# Evidence index

| Evidence file | Test or claim | Description |
|---|---|---|
| `logs/20261023-163147.raw` | T-02 | Raw serial-console log produced by `QemuBridge` while running `ls`. |
| `logs/20261023-163207.raw` | T-03 and T-04 | Raw serial-console log produced by `QemuBridge` while running `usertests`; the tick capture is in `logs/T-03-ticktest.raw`. |
| `logs/T-01-hello.raw` | T-01 | Captured `hello_test` output. |
| `logs/T-02-ping.out` | T-02 | Host-side printed `ls` result, including `README`, `hello_test`, and `ticktest`. |
| `logs/T-03-ticktest.raw` | T-03 | Tick output and stopwatch measurement. |
| `logs/T-04-usertests.raw` | T-04 | Post-`FSSIZE` usertests output containing `ALL TESTS PASSED`. |
| `docs/TEST_TABLE.md` | T-06, T-11, T-12 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
| `docs/TEST_TABLE.md` | T-07 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
| `docs/TEST_TABLE.md` | T-08 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
| `docs/TEST_TABLE.md` | T-09 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
| `docs/TEST_TABLE.md` | T-10 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
| `docs/TEST_TABLE.md` | T-13 | The historical raw capture is not retained; the final test table preserves the observed result and command. |
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
| `logs/20261026-020550.raw` | T-25 and T-28 | Retained successful real-QEMU workflow transcript with a successful result and command completion. |
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
| `results/archive/stage6_20261103/results.csv` | T-50 | Clean dry-run CSV with 12 rows; CPUS=1 succeeds and CPUS=3 is blocked by guest CPU detection. |
| `logs/T49-trace-wrap.raw` | T-49 | 70 workloads followed by `schedtrace 256`; no panic and 256 retained entries. |
| `logs/T51-kill-midrun.raw` | T-51 | Harness timeout classification and raw log after forced termination. |
| `logs/T52-resume.raw` | T-52 | Resume run skipped all 12 completed keys. |
| `logs/T53-interleave.raw` | T-53 | Concurrent second workflow rejected by admission; accepted RESULT remained intact. |
| `results/archive/stage6_20261103/gantt-edf-donate.png` | Visual/manual step 4 | Gantt chart generated from 200 trace entries containing donation markers. |
| `logs/stage8-injection.raw` | T-61, T-62 | Real host injection demonstration: benign pipeline completed and hostile input was read without being executed. |
| `logs/stage8-injection-bypass.raw` | T-62 | Direct guest command was rejected by kernel admission with `reason=slack` and the workflow-rejected message. |
| `logs/stage8-usertests-rr.raw` | T-63 | CPUS=1 `usertests` under RR; contains `ALL TESTS PASSED`. |
| `logs/stage8-usertests-edf.raw` | T-63 | CPUS=1 `usertests` under EDF; contains `ALL TESTS PASSED`. |
| `logs/stage8-usertests-edf_donate.raw` | T-63 | CPUS=1 `usertests` under EDF+Donate; contains `ALL TESTS PASSED`. |
| `results/archive/stage8-dry-run_20261107.csv` | T-61 | Six real-QEMU harness dry-run rows for the three policies at CPUS=1. |
| `dist/Team_Name_3.zip` | T-64 | Archive produced and inspected by the Stage 8 submission checker. |

<!-- stage7:begin -->
## Stage 7 graphs

Generated by `tools/index_evidence.py` from the `.sources.txt` sidecars in `results`. Do not edit between the markers by hand.

| Graph | CSV | Raw log directory | Commit hash | Rows used |
|---|---|---|---|---|
| `results/finish_box.png` | `results/results.csv`<br>`results/summary.csv` | `logs/run_20261111` | `d4cb4e4c` | 120 |
| `results/miss_vs_alpha.png` | `results/results.csv`<br>`results/summary.csv` | `logs/run_20261111` | `d4cb4e4c` | 240 |
| `results/misses_bar.png` | `results/results.csv`<br>`results/summary.csv` | `logs/run_20261111` | `d4cb4e4c` | 120 |
<!-- stage7:end -->

## Stage 7 Gantt charts and data

The Gantt PNGs have no `.sources.txt` sidecars, so they are listed here by hand. Each chain reads graph or table, then source file, then raw log location, then commit. Entries describe the PLAN-conformant second batch unless marked otherwise.

| Evidence file | Test or claim | Description |
|---|---|---|
| `results/archive/batch2_20261106/gantt-T57-edf.png` | T-57 | Raw trace `logs/run_20261106/gantt/T57-edf-trace.raw` (finish 90, deadline 72). The ring wrapped: 256 events, first seq 37. Commit d5f9314. |
| `results/archive/batch2_20261106/gantt-T58-edf_donate.png` | T-58 | Raw trace `logs/run_20261106/gantt/T58-edf_donate-trace.raw` (finish 45). The ring wrapped: 256 events, first seq 321. The log was saved under a mistaken name (`T57-edf-donate-trace.raw`) and renamed before commit; its content is unchanged. Commit d5f9314. |
| `results/results.csv` | T-54, T-55, T-56 | 210 rows, all status `ok`, 0 dropped, 0 duplicates, 0 miss mismatches; raw logs in `logs/run_20261106/`; `commit_hash` cb7a589b in every row. Committed in d5f9314. |
| `results/summary.csv`, `results/summary.md` | T-54, T-55, T-56 | Generated by `harness/analyze.py` from `results/results.csv`. Commit d5f9314. |
| `docs/results_template.md` | T-54, T-55, T-56 | Tables generated by `harness/analyze.py --fill-template` from `results/results.csv`; Explanation and Anomalies written by hand. |
| `results/archive/batch2_20261106/pilot_rev.csv`, `logs/stage7rev-pilot/` | Predictions Revision 2 | Pilot, 2 runs per cell, alpha 1.5, disclosed in `docs/predictions.md`; rows carry `commit_hash` 7fba9fae. Committed in cb7a589. Not part of the analysed batch. |
| `logs/stage7rev-calibration/` | W calibration | Runs 1-5 (46, 51, 50, 45, 49 ticks) give W = 48.2, SD 2.59; run 2 contains a mistyped command before the real one. Commit 7fba9fa. |
| `logs/audit.jsonl` (2026-11-06 adaptive records), `logs/20261106-085959.raw`, `logs/20261106-085959-*.run.raw`, `logs/20261106-090000-*.run.raw` | T-59 | Adaptive agent: rr pilot finish 98 > 72 (decision switch), edf_donate rerun finish 49 (decision compare), finish_delta -49 (decision done). Default machine type, CPUS=1. Commit f3ab258. |
| `results/archive/batch1_20261104/` | First batch (archived) | The first Stage 7 batch (`commit_hash` 043a34b5, `wfgen 4 100 1024`, W 24.4), its summaries, plots and side experiments; see `results/archive/batch1_20261104/README.md`. Raw logs remain in `logs/run_20261104/`, `logs/smoke_20261104/` and `logs/order_check_20261104/`. Data commit a314e13; archived in 066060f. |
| `logs/stage7-pilot/` | Kernel bug diagnosis | Pre-fix pilot: edf and edf_donate both finished at about deadline + 30 ticks for `wfgen 4 100 1024 D 3` on CPUS=1. Commit 305a13f. |
| `logs/stage7-fix/` | Fix regression checks | Post-fix usertests and donation tests; includes the hung run `usertests_rr_cpus1.raw` (L-28). Commit 305a13f. |
| `logs/stage7-calibration/` | Pre-fix calibration | Pre-fix W was 25.4 ticks. Commit 305a13f. |
| `logs/stage7-calibration-postfix/` | W calibration | Runs 2-6 (23, 27, 27, 22, 23 ticks) give W = 24.4, SD 2.41; run 1 was aborted by the operator before input and is kept. Commit 2dcf16c. |
| `logs/stage7-pilot-postfix/` | Choice of main alpha | Post-fix pilot used to choose alpha 1.5 (deadline 37), disclosed in `docs/predictions.md`. Commit 2dcf16c. |
| `results/archive/stage6_20261103/results.csv` (at the repository root until 2026-11-12) | Stage 6 note | Its `alpha` column was a label only; deadline 300 was always sent. |

## Final verification (2026-11-11)

Evidence for the final kernel (commit `d4cb4e4c`). It supersedes the Stage 5
donation logs and the Stage 7 batch wherever the two disagree.

| Evidence | Tests | What it shows |
|---|---|---|
| `logs/final_20261111/smoke-cpus1.raw` | T-66, T-67, T-69 | CPUS=1: boot policy 2; `wftest`, `test_negative`, `donate5`, `cycletest`, `killtest`, `donatetest` and `usertests` pass. |
| `logs/final_20261111/smoke-cpus3.raw` | T-66, T-67, T-68 | CPUS=3: the same tests except `usertests`; `cycletest` prints `donate: cycle`. |
| `docs/gdb/slot-leak-before.txt` | T-70 | GDB at `sys_setworkflow_impl` on `e530df7`: a refused call leaves `workflows[1]` with `wid = 1, nmembers = 0`, and the next valid call returns -1. |
| `docs/gdb/slot-leak-after.txt` | T-70 | The same session on the fixed kernel: the table stays empty after the refusal and the valid call returns 0. |
| `results/results.csv` | T-71 | 480 runs: alpha 1.2, 1.5, 2.0, 3.0; CPUS 1 and 3; three policies; 20 runs per cell; all `ok`. |
| `results/summary.md` | T-71 | Misses, miss rate, bootstrap interval and finish time per cell; Fisher's exact test. |
| `logs/run_20261111` | T-71 | One raw QEMU log per run of the final batch. |
| `results/README.md` | T-71 | Written summary of the final batch. |
| `docs/report/report.pdf` | | Submitted project report; source in `docs/report/report.tex`. |
