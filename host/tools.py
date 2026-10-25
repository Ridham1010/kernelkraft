"""Fixed guest command templates and host-only actions."""


def _ls(args):
    return ["ls"]


def _cat(args):
    return ["cat", args["path"]]


def _policy(args):
    return ["schedctl", args["policy"]]


def _pipeline(args):
    return [
        "wfgen",
        str(args["stages"]),
        str(args["work"]),
        str(args["bytes"]),
        str(args["deadline"]),
        str(args["hogs"]),
    ]


def _stats(args):
    return ["schedstat"]


TOOLS = {
    "list_files": {"args": {}, "build": _ls, "host_only": False},
    "read_file": {"args": {"path": "path"}, "build": _cat, "host_only": False},
    "set_policy": {"args": {"policy": "policy"}, "build": _policy, "host_only": False},
    "run_pipeline": {
        "args": {
            "stages": "int",
            "work": "int",
            "bytes": "int",
            "deadline": "int",
            "hogs": "int",
        },
        "build": _pipeline,
        "host_only": False,
    },
    "sched_stats": {"args": {}, "build": _stats, "host_only": False},
    "summarize": {"args": {"text": "text"}, "build": None, "host_only": True},
}
