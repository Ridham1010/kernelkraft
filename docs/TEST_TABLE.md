| ID | Stage | Test | Input | Expected | Observed | Evidence file | Type |
|---|---:|---|---|---|---|---|---|
| T-00a | 0 | `usertests` on the untouched tree | Clean worktree at `baseline`; `make -C xv6-public qemu-nox CPUS=1`; run `usertests` | `ALL TESTS PASSED` | Passed; output contains `ALL TESTS PASSED` | `logs/baseline_usertests.raw` | Regression |
| T-00b | 0 | `tools/check_submission.sh 0` | Run from repository root | Passes | Passed, exit 0; created `dist/Team_Name_3.zip` | `logs/T-00b-check-submission.raw` | Tooling |
| T-00c | 0 | `python3 -c "import host.config"` | Run from repository root | Loads without error | Passed, exit 0 | `logs/T-00c-host-config.raw` | Host |
| T-01 | 1 | `hello_test` in xv6 | Run through QEMU | Prints `hello from kernel` then `hello() returned 0` | Passed; exact output observed | `logs/T-01-hello.raw` | Functional |
| T-02 | 1 | `python3 host/ping.py` | Run from repository root | Prints the `ls` listing including `README`, `hello_test` | Passed; listing includes `README`, `hello_test`, and `ticktest` | `logs/T-02-ping.out` | Host |
| T-03 | 1 | `ticktest` | Run through QEMU | Prints a tick difference of about 500; compute ticks/second from the stopwatch | Passed; difference 500, stopwatch 5.106 seconds, approximately 97.9 ticks/second | `logs/T-03-ticktest.raw` | Timing |
| T-04 | 1 | `usertests` after `FSSIZE` change | Run through QEMU | `ALL TESTS PASSED` | Passed; exact success line observed | `logs/T-04-usertests.raw` | Regression |
| T-05 | 2 | Remove the `UPROGS` entry temporarily | Rebuild and run `hello_test`, then restore | `hello_test: not found`; restore succeeds | PENDING |  | Negative |