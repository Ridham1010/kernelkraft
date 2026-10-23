"""A small pexpect bridge for the xv6 serial console."""

from datetime import datetime
import re
from pathlib import Path

import pexpect

try:
    from host.config import load_config
except ImportError:
    from config import load_config


class QemuBridge:
    """Start xv6 through Make and exchange bounded commands with its shell."""

    prompt = re.compile(r"\$ ")
    init_line = "init: starting sh"

    def __init__(self, config_path=None):
        self.config = load_config(config_path) if config_path else load_config()
        self.child = None
        self.log_file = None

    def start(self, cpus=1):
        """Build and start xv6, then wait for the shell prompt."""
        if type(cpus) is not int or cpus <= 0:
            raise ValueError("cpus must be a positive integer")
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
        self.child.logfile_read = self.log_file
        self.child.expect(self.init_line)
        self.child.expect(self.prompt)

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
