import pytest

from host.audit import AuditLog
from host.bridge.qemu_bridge import Observation, QemuBridge
from host.loop import AgentLoop
from host.planners.deterministic import DeterministicPlanner
from host.validator import ValidationError, validate_action


def call(tool, args):
    return {"tool": tool, "args": args}


def test_unknown_tool():
    with pytest.raises(ValidationError):
        validate_action(call("rm_all", {}))


def test_missing_and_extra_args():
    with pytest.raises(ValidationError):
        validate_action(call("read_file", {}))
    with pytest.raises(ValidationError):
        validate_action(call("list_files", {"x": 1}))


@pytest.mark.parametrize(
    "path", ["../x", "../etc/passwd", "/a/b", "abcdefghijklmnopqrst", "/notinallowlist"]
)
def test_bad_paths(path):
    with pytest.raises(ValidationError):
        validate_action(call("read_file", {"path": path}))


def test_wrong_type_and_bool():
    with pytest.raises(ValidationError):
        validate_action(call("read_file", {"path": 1}))
    args = {"stages": True, "work": 1, "bytes": 1, "deadline": 20, "hogs": 0}
    with pytest.raises(ValidationError):
        validate_action(call("run_pipeline", args))


def test_pipeline_bounds():
    base = {"stages": 2, "work": 1, "bytes": 1, "deadline": 1, "hogs": 0}
    with pytest.raises(ValidationError):
        validate_action(call("run_pipeline", base))
    base["deadline"] = 20
    base["hogs"] = 99
    with pytest.raises(ValidationError):
        validate_action(call("run_pipeline", base))


def test_valid_call():
    action = call("run_pipeline", {"stages": 2, "work": 1, "bytes": 1, "deadline": 20, "hogs": 0})
    assert validate_action(action) == action


def test_package_bridge_defines_observation():
    assert Observation("ok", "", 0).status == "ok"


class _Match:
    def __init__(self, value):
        self.value = value

    def group(self, index):
        assert index == 0
        return self.value


class _ExecFailChild:
    def __init__(self):
        self.before = "xrun deadbeef missing\n"
        self.match = None
        self.expect_calls = 0
        self.logfile_read = None

    def sendline(self, command):
        assert command == "xrun deadbeef missing"

    def expect(self, patterns, timeout):
        self.expect_calls += 1
        if self.expect_calls == 1:
            self.match = _Match("@@EXECFAIL deadbeef")
        elif self.expect_calls == 2:
            self.match = _Match("@@DONE deadbeef")
        else:
            self.match = _Match("$ ")


def test_execfail_consumes_done_and_prompt(monkeypatch):
    monkeypatch.setattr("host.bridge.qemu_bridge.secrets.token_hex", lambda size: "deadbeef")
    bridge = object.__new__(QemuBridge)
    bridge.child = _ExecFailChild()
    observation = bridge.run(["missing"])
    assert observation.status == "error"
    assert bridge.child.expect_calls == 3


class _DoneChild:
    def __init__(self):
        self.before = ""
        self.match = None
        self.logfile_read = None
        self.command = ""

    def sendline(self, command):
        self.command = command
        self.before = command + "\n"

    def expect(self, patterns, timeout):
        if isinstance(patterns, list):
            nonce = self.command.split()[1]
            self.match = _Match("@@DONE " + nonce)
        else:
            self.match = _Match("$ ")


def test_run_creates_separate_raw_logs(monkeypatch, tmp_path):
    paths = []

    def open_run_log(bridge, nonce):
        path = tmp_path / (nonce + ".raw")
        paths.append(path)
        return path, path.open("w", encoding="utf-8")

    monkeypatch.setattr(QemuBridge, "_open_run_log", open_run_log)
    nonces = iter(("11111111", "22222222"))
    monkeypatch.setattr("host.bridge.qemu_bridge.secrets.token_hex", lambda size: next(nonces))
    bridge = object.__new__(QemuBridge)
    bridge.child = _DoneChild()
    bridge.run(["ls"])
    bridge.run(["ls"])
    assert paths[0] != paths[1]
    assert paths[0].exists()
    assert paths[1].exists()


def test_restart_preserves_active_cpu_count():
    bridge = object.__new__(QemuBridge)
    bridge.cpus = 3
    bridge.child = object()
    calls = []
    bridge.close = lambda: calls.append("close")
    bridge.start = lambda cpus=1: calls.append(cpus)
    bridge.restart()
    assert calls == ["close", 3]


class _FakeBridge:
    def __init__(self, output="ok\n"):
        self.output = output
        self.calls = []

    def run(self, argv):
        self.calls.append(argv)
        return Observation("ok", self.output, 0.01)


class _Planner:
    def plan(self, request, state):
        return {"tool": "rm_all", "args": {}}


def test_injected_planner_reads_inbox_then_proposes_pipeline():
    planner = DeterministicPlanner("injected")
    state = {"actions": [], "read_paths": [], "injected": False}
    assert planner.plan("read /inbox.txt", state)["tool"] == "list_files"
    state["actions"].append({"tool": "list_files", "args": {}})
    assert planner.plan("read /inbox.txt", state)["args"]["path"] == "/inbox.txt"
    state["read_paths"].append("/inbox.txt")
    assert planner.plan("read /inbox.txt", state)["tool"] == "run_pipeline"


def test_rejected_action_does_not_call_bridge(tmp_path):
    bridge = _FakeBridge()
    state = AgentLoop(
        bridge, _Planner(), audit=AuditLog(tmp_path / "audit.jsonl"), max_steps=1, execution_source="fake"
    ).run("bad request")
    assert bridge.calls == []
    assert state["observations"] == []


def test_missing_file_is_semantic_error_and_is_reported(tmp_path):
    class _ReadPlanner:
        def plan(self, request, state):
            if not state["actions"]:
                return {"tool": "read_file", "args": {"path": "/report.txt"}}
            return None

    bridge = _FakeBridge("cat: cannot open /report.txt\n")
    state = AgentLoop(
        bridge, _ReadPlanner(), audit=AuditLog(tmp_path / "audit.jsonl"), execution_source="fake"
    ).run("read /report.txt")
    assert state["observations"] == [{
        "tool": "read_file",
        "status": "error",
        "output": "cat: cannot open /report.txt\n",
    }]
    record = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert '"execution_source": "fake"' in record
    assert '"observation_status": "error"' in record
