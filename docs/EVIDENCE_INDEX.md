# Evidence index

| Evidence file | Test or claim | Description |
|---|---|---|
| `logs/20261023-163147.raw` | T-02 | Raw serial-console log produced by `QemuBridge` while running `ls`. |
| `logs/20261023-163207.raw` | T-03 and T-04 | Raw serial-console log produced by `QemuBridge` while running `usertests`; the tick capture is in `logs/T-03-ticktest.raw`. |
| `logs/T-01-hello.raw` | T-01 | Captured `hello_test` output. |
| `logs/T-02-ping.out` | T-02 | Host-side printed `ls` result, including `README`, `hello_test`, and `ticktest`. |
| `logs/T-03-ticktest.raw` | T-03 | Tick output and stopwatch measurement. |
| `logs/T-04-usertests.raw` | T-04 | Post-`FSSIZE` usertests output containing `ALL TESTS PASSED`. |
| `logs/20261025-211404.raw` | T-06, T-11, T-12 | EDF run: child A (deadline 100) finished at tick 250 before child B (deadline 200) at tick 458; the same session records `setsched(7) = -1`, `setworkflow(1,0) = -1`, and the second `setworkflow` call returning `-1`. |
| `logs/20261025-212038.raw` | T-07 | RR run: child B finished at tick 532 and child A at tick 534. |
| `logs/20261025-211715.raw` | T-08 | EDF + usertests: `ALL TESTS PASSED`. |
| `logs/20261025-211536.raw` | T-09 | RR + usertests: `ALL TESTS PASSED`. |
| `logs/20261025-211846.raw` | T-10 | EDF_Donate + usertests: `ALL TESTS PASSED`. |
| `logs/20261025-212854.raw` | T-13 | Three-CPU QEMU bridge session completed and was terminated without a panic being observed. |
