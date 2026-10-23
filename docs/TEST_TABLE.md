| ID | Stage | Test | Input | Expected | Observed | Evidence file | Type |
|---|---:|---|---|---|---|---|---|
| T-01 | 0 | `hello_test` in xv6 | Run through QEMU | Prints `hello from kernel` then `hello() returned 0` | PENDING |  | Functional |
| T-02 | 0 | `python host/ping.py` | Run from repository root | Prints the `ls` listing including `README`, `hello_test` | PENDING |  | Host |
| T-03 | 0 | `ticktest` | Run through QEMU | Prints a tick difference of about 500; compute ticks/second from stopwatch | PENDING |  | Timing |
| T-04 | 0 | `usertests` after `FSSIZE` change | Run through QEMU | `ALL TESTS PASSED` | PENDING |  | Regression |
| T-05 | 0 | Remove `UPROGS` entry temporarily | Rebuild and run `hello_test`, then restore entry | `hello_test: not found`; restore succeeds | PENDING |  | Negative |