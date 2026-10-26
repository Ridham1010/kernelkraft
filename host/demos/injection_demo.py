"""Run the Stage 4 benign/injected demonstrations and inspect a manual bypass log."""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.bridge.qemu_bridge import QemuBridge
from host.config import load_config
from host.loop import AgentLoop
from host.planners.deterministic import DeterministicPlanner


MANUAL_COMMAND = "wfgen 3 200 4096 1 8"


def has_admission_rejection(log_path):
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    return re.search(r"^admit: rejected .*", text, re.MULTILINE) is not None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-log", help="raw log captured after the manual bypass")
    args = parser.parse_args()
    if args.check_log:
        print("manual bypass admission rejection: %s" %
              ("yes" if has_admission_rejection(args.check_log) else "no"))
        return

    bridge = QemuBridge()
    bridge.start()
    try:
        benign = AgentLoop(
            bridge,
            DeterministicPlanner("normal"),
            load_config(),
            execution_source="qemu",
        ).run("set_policy edf then run_pipeline")
        print("benign:", benign["observations"])

        injected = AgentLoop(
            bridge,
            DeterministicPlanner("injected"),
            load_config(),
            execution_source="qemu",
        ).run("list files then read /inbox.txt")
        print("injected:", injected["observations"])
        print("Type this manually at the xv6 prompt to bypass the host validator:")
        print(MANUAL_COMMAND)
        print("Then run: python3 host/demos/injection_demo.py --check-log <raw-log>")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
