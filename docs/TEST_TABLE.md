| ID | Stage | Test | Input | Expected | Observed | Evidence file | Type |
|---|---:|---|---|---|---|---|---|
| T-00a | 0 | `usertests` on the untouched tree | Clean worktree at `baseline`; `make -C xv6-public qemu-nox CPUS=1`; run `usertests` | `ALL TESTS PASSED` | Passed; output contains `ALL TESTS PASSED` | `logs/baseline_usertests.raw` | Regression |
| T-00b | 0 | `tools/check_submission.sh 0` | Run from repository root | Passes | Passed, exit 0; created `dist/Team_Name_3.zip` | `logs/T-00b-check-submission.raw` | Tooling |
| T-00c | 0 | `python3 -c "import host.config"` | Run from repository root | Loads without error | Passed, exit 0 | `logs/T-00c-host-config.raw` | Host |
| T-01 | 0 | `hello_test` in xv6 | Run through QEMU | Prints `hello from kernel` then `hello() returned 0` | PENDING |  | Functional |
| T-02 | 0 | `python host/ping.py` | Run from repository root | Prints the `ls` listing including `README`, `hello_test` | PENDING |  | Host |
| T-03 | 0 | `ticktest` | Run through QEMU | Prints a tick difference of about 500; compute ticks/second from stopwatch | PENDING |  | Timing |
| T-04 | 0 | `usertests` after `FSSIZE` change | Run through QEMU | `ALL TESTS PASSED` | PENDING |  | Regression |
| T-05 | 0 | Remove `UPROGS` entry temporarily | Rebuild and run `hello_test`, then restore entry | `hello_test: not found`; restore succeeds | PENDING |  | Negative |