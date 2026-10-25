"""A small pexpect bridge for the xv6 serial console."""

from datetime import datetime
from dataclasses import dataclass
import re
from pathlib import Path
import secrets
import time

import pexpect

try:
    from host.config import load_config
except ImportError:
    from config import load_config


@dataclass
class Observation:
    status: str
    output: str
    elapsed: float


class _LogTee:
    def __init__(self, *streams):
        self.streams = tuple(stream for stream in streams if stream is not None)

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


class QemuBridge:
    """Start xv6 through Make and exchange bounded commands with its shell."""

    prompt = re.compile(r"\$ ")
    init_line = "init: starting sh"

    def __init__(self, config_path=None):
        self.config = load_config(config_path) if config_path else load_config()
        self.child = None
        self.log_file = None
        self.cpus = 1
        self.last_run_log_path = None

    def start(self, cpus=1):
        """Build and start xv6, then wait for the shell prompt."""
        if cpus not in (1, 3):
            raise ValueError("cpus must be 1 or 3")
        allowed = self.config.get("cpus_allowed")
        if allowed is not None and cpus not in allowed:
            raise ValueError("cpus is not allowed by host/config.json")

        xv6_dir = Path(self.config["xv6_dir"])
        if not xv6_dir.is_absolute():
            xv6_dir = Path(__file__).resolve().parents[2] / xv6_dir
        command = ["make", "qemu-nox", "CPUS=%d" % cpus]
        qemu_bin = self.config.get("qemu_bin")
        if qemu_bin is not None:
            if not isinstance(qemu_bin, str) or not qemu_bin:
                raise ValueError("qemu_bin must be a non-empty string or null")
            command.append("QEMU=%s" % qemu_bin)
        if self.config.get("snapshot", False):
            command.append("QEMUEXTRA=-snapshot")

        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file = (log_dir / (timestamp + ".raw")).open(
            "w", encoding="utf-8", errors="replace"
        )
        self.child = pexpect.spawn(
            command[0],
            command[1:],
            cwd=str(xv6_dir),
            encoding="utf-8",
            codec_errors="replace",
            timeout=180,
        )
        self.cpus = cpus
        self.child.logfile_read = self.log_file
        self.child.expect(self.init_line)
        self.child.expect(self.prompt)

    def restart(self, cpus=None):
        """Replace a crashed or wedged guest with a fresh instance."""
        if cpus is None:
            cpus = self.cpus
        if cpus not in (1, 3):
            raise ValueError("cpus must be 1 or 3")
        self.close()
        self.start(cpus)

    def _open_run_log(self, nonce):
        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = log_dir / ("%s-%s.run.raw" % (timestamp, nonce))
        return path, path.open("w", encoding="utf-8", errors="replace")

    def run(self, argv, timeout=30):
        """Run a validated guest argv, using a nonce that the guest must echo."""
        if self.child is None:
            raise RuntimeError("QEMU bridge is not started")
        if not isinstance(argv, list) or not argv or any(
            not isinstance(item, str) for item in argv
        ):
            raise ValueError("argv must be a non-empty list of strings")
        nonce = secrets.token_hex(4)
        command = "xrun %s %s" % (nonce, " ".join(argv))
        if len(command) >= 90:
            raise ValueError("guest command must be shorter than 90 characters")
        started = time.monotonic()
        session_log = self.child.logfile_read
        run_log_path, run_log = self._open_run_log(nonce)
        self.last_run_log_path = run_log_path
        self.child.logfile_read = _LogTee(session_log, run_log)
        result = None
        restart_needed = False
        try:
            self.child.sendline(command)
            self.child.expect(
                [
                    re.escape("@@DONE " + nonce),
                    re.escape("@@EXECFAIL " + nonce),
                    r"panic:",
                    r"--kill proc",
                    self.prompt,
                ],
                timeout=timeout,
            )
            text = self.child.before.replace("\r", "")
            if not text.lstrip().startswith(command):
                raise RuntimeError("guest command echo did not match")
            output = text[text.find("\n") + 1 :] if "\n" in text else ""
            match = self.child.match
            if match is not None and match.group(0).startswith("@@DONE"):
                self.child.expect(self.prompt, timeout=timeout)
                result = Observation("ok", output, time.monotonic() - started)
            elif match is not None and match.group(0).startswith("@@EXECFAIL"):
                self.child.expect(re.escape("@@DONE " + nonce), timeout=timeout)
                self.child.expect(self.prompt, timeout=timeout)
                result = Observation("error", output, time.monotonic() - started)
            else:
                status = "panic" if match is not None and match.group(0) == "panic:" else "error"
                result = Observation(status, output, time.monotonic() - started)
                restart_needed = True
        except (pexpect.TIMEOUT, pexpect.EOF):
            result = Observation("timeout", "", time.monotonic() - started)
            restart_needed = True
        except RuntimeError:
            result = Observation("protocol_error", "", time.monotonic() - started)
            restart_needed = True
        finally:
            if self.child is not None:
                self.child.logfile_read = session_log
            run_log.close()
        if restart_needed:
            self.restart()
        return result

    def run_raw(self, cmd, timeout=15):
        """Run one guest command and return output without its echo."""
        if self.child is None:
            raise RuntimeError("QEMU bridge is not started")
        if not isinstance(cmd, str) or len(cmd) >= 90:
            raise ValueError("guest command must be shorter than 90 characters")
        self.child.sendline(cmd)
        self.child.expect(self.prompt, timeout=timeout)
        text = self.child.before.replace("\r", "")
        if text.startswith(cmd + "\n"):
            text = text[len(cmd) + 1 :]
        else:
            lines = text.splitlines(True)
            if lines and lines[0].strip() == cmd:
                text = "".join(lines[1:])
        return text

    def close(self):
        """Exit the guest shell and terminate QEMU if it remains alive."""
        if self.child is None:
            return
        try:
            self.child.sendcontrol("a")
            self.child.send("x")
            self.child.expect(pexpect.EOF, timeout=10)
        except (pexpect.TIMEOUT, pexpect.EOF):
            if self.child.isalive():
                self.child.terminate(force=True)
        finally:
            if self.log_file is not None:
                self.log_file.close()
                self.log_file = None
            self.child = None
