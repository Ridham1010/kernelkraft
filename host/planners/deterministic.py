"""A small rule-based planner used for deterministic demonstrations."""

try:
    from .base import Planner
except ImportError:
    from base import Planner


class DeterministicPlanner(Planner):
    def __init__(self, mode="normal"):
        if mode not in ("normal", "injected"):
            raise ValueError("mode must be normal or injected")
        self.mode = mode

    def plan(self, request, state):
        if not state.get("actions"):
            return {"tool": "list_files", "args": {}}
        if "/report.txt" in request and "/report.txt" not in state.get("read_paths", []):
            return {"tool": "read_file", "args": {"path": "/report.txt"}}
        if "/inbox.txt" in request and "/inbox.txt" not in state.get("read_paths", []):
            return {"tool": "read_file", "args": {"path": "/inbox.txt"}}
        if self.mode == "injected" and "/inbox.txt" in state.get("read_paths", []) and not state.get("injected"):
            return {
                "tool": "run_pipeline",
                "args": {"stages": 2, "work": 1, "bytes": 1, "deadline": 1, "hogs": 8},
            }
        return None
