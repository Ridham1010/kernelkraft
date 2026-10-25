"""Validate planner actions before they can reach the guest."""

import re

try:
    from host.config import load_config
    from host.tools import TOOLS
except ImportError:
    from config import load_config
    from tools import TOOLS


class ValidationError(ValueError):
    """A proposed action violates the host policy."""


_PATH = re.compile(r"^/?[A-Za-z0-9._]{1,14}$")
_POLICIES = ("rr", "edf", "edf_donate")


def validate_action(action, config=None):
    config = config or load_config()
    if not isinstance(action, dict):
        raise ValidationError("action must be an object")
    tool = action.get("tool")
    args = action.get("args")
    if tool not in TOOLS:
        raise ValidationError("unknown tool")
    if not isinstance(args, dict):
        raise ValidationError("args must be an object")
    spec = TOOLS[tool]["args"]
    if set(args) != set(spec):
        raise ValidationError("missing or extra arguments")
    result = dict(args)
    if tool == "read_file":
        path = result["path"]
        if not isinstance(path, str) or not _PATH.fullmatch(path):
            raise ValidationError("invalid path")
        if path not in config.get("allowlist", []):
            raise ValidationError("path is not allowlisted")
    elif tool == "set_policy":
        if result["policy"] not in _POLICIES:
            raise ValidationError("invalid policy")
    elif tool == "summarize":
        if not isinstance(result["text"], str):
            raise ValidationError("text must be a string")
    elif tool == "run_pipeline":
        for name in spec:
            if type(result[name]) is not int:
                raise ValidationError("%s must be an integer" % name)
        limits = {
            "stages": (config["MIN_STAGES"], config["MAX_STAGES"]),
            "work": (config["MIN_WORK"], config["MAX_WORK"]),
            "bytes": (config["MIN_BYTES"], config["MAX_BYTES"]),
            "deadline": (config["MIN_SLACK"], config["NO_DEADLINE"]),
            "hogs": (0, config["MAX_HOGS"]),
        }
        for name, (lower, upper) in limits.items():
            value = result[name]
            if value < lower or value > upper:
                if config.get("clamp"):
                    result[name] = min(upper, max(lower, value))
                else:
                    raise ValidationError("%s is out of range" % name)
    return {"tool": tool, "args": result}
