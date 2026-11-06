"""AdaptivePlanner tests with a fake bridge (no QEMU)."""

import json

from host.audit import AuditLog
from host.bridge.qemu_bridge import Observation
from host.loop import AgentLoop
from host.planners.adaptive import MAX_STEPS, AdaptivePlanner

WORKLOAD = {"stages": 4, "work": 100, "bytes": 1024, "deadline": 37, "hogs": 3}
POLICY_NUMBER = {"rr": 0, "edf": 1, "edf_donate": 2}


class FakeBridge:
    """Answers schedctl/wfgen like the guest; finish per policy is scripted."""

    def __init__(self, finish_by_policy, status="ok"):
        self.finish_by_policy = finish_by_policy
        self.status = status
        self.policy = "rr"
        self.calls = []

    @staticmethod
    def miss_for(finish, deadline):
        # wfgen's rule: miss = finish > deadline.
        return 1 if finish > deadline else 0

    def run(self, argv):
        self.calls.append(argv)
        if argv[0] == "schedctl":
            self.policy = argv[1]
            return Observation(self.status, "", 0.01)
        if argv[0] == "wfgen":
            finish = self.finish_by_policy[self.policy]
            miss = self.miss_for(finish, int(argv[4]))
            output = "RESULT policy=%d cpus=1 finish=%d deadline=%s miss=%d\n" % (
                POLICY_NUMBER[self.policy], finish, argv[4], miss)
            return Observation(self.status, output, 0.01)
        raise AssertionError("unexpected guest command %r" % argv)


def run(tmp_path, bridge):
    audit = AuditLog(tmp_path / "audit.jsonl")
    planner = AdaptivePlanner(WORKLOAD, audit)
    state = AgentLoop(bridge, planner, audit=audit, execution_source="fake").run("ignored")
    records = [json.loads(line) for line in
               (tmp_path / "audit.jsonl").read_text().splitlines()]
    decisions = [r for r in records if r.get("planner") == "adaptive"]
    return planner, state, records, decisions


def test_miss_switches_and_reruns(tmp_path):
    bridge = FakeBridge({"rr": 50, "edf_donate": 30})
    planner, state, records, decisions = run(tmp_path, bridge)
    assert bridge.calls == [
        ["schedctl", "rr"], ["wfgen", "4", "100", "1024", "37", "3"],
        ["schedctl", "edf_donate"], ["wfgen", "4", "100", "1024", "37", "3"],
    ]
    assert [d["decision"] for d in decisions] == ["switch", "compare", "done"]
    assert decisions[0]["parsed"]["finish"] == 50 and decisions[0]["host_miss"] == 1
    assert decisions[1]["policy"] == "edf_donate" and decisions[1]["host_miss"] == 0
    assert state["actions"][-1]["tool"] == "summarize"
    assert "switch helped" in state["actions"][-1]["args"]["text"]
    # AgentLoop's own per-tool records are written to the same audit file.
    assert sum(1 for r in records if "validated_call" in r) == 5


def test_no_miss_stops_after_pilot(tmp_path):
    # finish == deadline is not a miss under the host rule.
    bridge = FakeBridge({"rr": 37, "edf_donate": 30})
    planner, state, records, decisions = run(tmp_path, bridge)
    assert bridge.calls == [["schedctl", "rr"], ["wfgen", "4", "100", "1024", "37", "3"]]
    assert [d["decision"] for d in decisions] == ["stop"]
    assert decisions[0]["host_miss"] == 0


def test_inconsistent_miss_aborts(tmp_path):
    # RESULT says miss=0 although finish 50 > deadline 37: do not trust it.
    class LyingBridge(FakeBridge):
        @staticmethod
        def miss_for(finish, deadline):
            return 0

    bridge = LyingBridge({"rr": 50, "edf_donate": 30})
    _, _, _, decisions = run(tmp_path, bridge)
    assert [d["decision"] for d in decisions] == ["abort"]
    assert "disagrees" in decisions[0]["reason"]
    assert len(bridge.calls) == 2


def test_parsed_fields_have_no_miss_kernel(tmp_path):
    bridge = FakeBridge({"rr": 50, "edf_donate": 30})
    _, _, records, decisions = run(tmp_path, bridge)
    assert set(decisions[0]["parsed"]) == {"policy", "cpus", "finish", "deadline", "miss"}
    assert decisions[0]["parsed"]["miss"] == decisions[0]["host_miss"] == 1
    assert not any("miss_kernel" in json.dumps(r) for r in records)


def test_never_more_than_three_steps(tmp_path):
    bridge = FakeBridge({"rr": 90, "edf_donate": 90})
    planner, state, records, decisions = run(tmp_path, bridge)
    assert len(planner.steps) <= MAX_STEPS == 3
    assert len(decisions) <= MAX_STEPS
    assert "did not help" in state["actions"][-1]["args"]["text"]
    assert planner.plan("again", state) is None


def test_failed_command_aborts(tmp_path):
    bridge = FakeBridge({"rr": 50, "edf_donate": 30}, status="error")
    planner, state, records, decisions = run(tmp_path, bridge)
    assert [d["decision"] for d in decisions] == ["abort"]
    assert len(bridge.calls) == 1


def test_timeout_stops_loop(tmp_path):
    # AgentLoop itself stops on timeout/panic before asking the planner again.
    bridge = FakeBridge({"rr": 50, "edf_donate": 30}, status="timeout")
    planner, state, records, decisions = run(tmp_path, bridge)
    assert len(bridge.calls) == 1
    assert decisions == []
    assert records[-1]["observation_status"] == "timeout"


def test_wrong_policy_in_result_aborts(tmp_path):
    class StuckBridge(FakeBridge):
        def run(self, argv):
            if argv[0] == "schedctl":
                self.calls.append(argv)
                return Observation("ok", "", 0.01)  # policy silently unchanged
            return FakeBridge.run(self, argv)

    bridge = StuckBridge({"rr": 50, "edf_donate": 30})
    _, _, _, decisions = run(tmp_path, bridge)
    assert [d["decision"] for d in decisions] == ["switch", "abort"]
