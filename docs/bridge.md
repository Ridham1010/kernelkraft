# QEMU bridge

[`host/bridge/qemu_bridge.py`](../host/bridge/qemu_bridge.py) starts xv6 with
`make qemu-nox CPUS=<cpus>` in the configured xv6 directory. It waits for
`init: starting sh`, then waits for the xv6 shell prompt `$ ` before sending
commands.

`run_raw()` accepts guest command lines shorter than 90 characters, waits for
the next `$ ` prompt, removes the echoed command and carriage returns, and
returns the command output. Startup uses a generous 120-second timeout;
individual commands default to 15 seconds.

All bytes read from the child process are written to a timestamped
`logs/*.raw` file through `pexpect.logfile_read`. `close()` sends Ctrl-A then
`x` to QEMU and force-terminates it if it does not exit promptly.
