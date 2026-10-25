"""Append structured evidence for every planner step."""

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path=None):
        self.path = Path(path or Path(__file__).resolve().parents[1] / "logs" / "audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record):
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, sort_keys=True) + "\n")


def kernel_log_lines(output):
    return [
        line for line in output.splitlines()
        if line.startswith(("donate:", "admit:", "sched:"))
    ]
