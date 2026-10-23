# Evidence index

| Evidence file | Test or claim | Description |
|---|---|---|
| `logs/20261023-163147.raw` | T-02 | Raw serial-console log produced by `QemuBridge` while running `ls`. |
| `logs/20261023-163207.raw` | T-03 and T-04 | Raw serial-console log produced by `QemuBridge` while running `usertests`; the tick capture is in `logs/T-03-ticktest.raw`. |
| `logs/T-01-hello.raw` | T-01 | Captured `hello_test` output. |
| `logs/T-02-ping.out` | T-02 | Host-side printed `ls` result, including `README`, `hello_test`, and `ticktest`. |
| `logs/T-03-ticktest.raw` | T-03 | Tick output and stopwatch measurement. |
| `logs/T-04-usertests.raw` | T-04 | Post-`FSSIZE` usertests output containing `ALL TESTS PASSED`. |
