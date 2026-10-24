# Evidence index

| Evidence file | Test or claim | Description |
|---|---|---|
| `logs/20261023-163147.raw` | T-02 | Raw serial-console log produced by `QemuBridge` while running `ls`. |
| `logs/20261023-163207.raw` | T-03 and T-04 | Raw serial-console log produced by `QemuBridge` while running `usertests`; the tick capture is in `logs/T-03-ticktest.raw`. |
| `logs/T-01-hello.raw` | T-01 | Captured `hello_test` output. |
| `logs/T-02-ping.out` | T-02 | Host-side printed `ls` result, including `README`, `hello_test`, and `ticktest`. |
| `logs/T-03-ticktest.raw` | T-03 | Tick output and stopwatch measurement. |
| `logs/T-04-usertests.raw` | T-04 | Post-`FSSIZE` usertests output containing `ALL TESTS PASSED`. |
| `logs/T-06-edftest.raw` | T-06 | EDF scheduler: child A (deadline 100) finished at tick 1370, child B (deadline 200) at 1423. |
| `logs/T-07-edftest.raw` | T-07 | RR scheduler: both children finished at tick 7191. |
| `logs/T-08-usertests.raw` | T-08 | EDF + usertests: ALL TESTS PASSED. |
| `logs/T-09-usertests.raw` | T-09 | RR + usertests: ALL TESTS PASSED. |
| `logs/T-10-usertests.raw` | T-10 | EDF_Donate + usertests: ALL TESTS PASSED. |
| `logs/T-11-negative.raw` | T-11 | setsched(7) returns -1. |
| `logs/T-12-negative.raw` | T-12 | setworkflow(1,0)=-1, second call=-1. |
| `logs/T-13-cpus3.raw` | T-13 | Boot with CPUS=3: no panic, 3 CPUs started. |

