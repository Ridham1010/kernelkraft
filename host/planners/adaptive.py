"""Adaptive planner: rr pilot, switch to edf_donate on a miss, compare.

Every decision is plain code over integers parsed from the RESULT line; the
request text and any model output are ignored. The RESULT miss field (which
wfgen computes as finish > deadline) is used only after it is checked
against finish > deadline; a disagreement aborts. A "step" is one decision
phase: 1 = pilot under rr, 2 = rerun under edf_donate, 3 = comparison. Each
phase writes one record through the existing AuditLog, in addition to the
per-tool records AgentLoop writes.
"""

import re

try:
    from .base import Planner
except ImportError:
    from base import Planner

MAX_STEPS = 3
PILOT_POLICY = "rr"
SWITCH_POLICY = "edf_donate"
POLICY_NUMBER = {"rr": 0, "edf": 1, "edf_donate": 2}
WORKLOAD_KEYS = ("stages", "work", "bytes", "deadline", "hogs")
RESULT_LINE = re.compile(
    r"^RESULT policy=(\d+) cpus=(\d+) finish=(\d+) deadline=(\d+) miss=(\d+)\r?$",
    re.MULTILINE,
)


def parse_result(output):
    """Return the integer fields of exactly one RESULT line, else None."""
    matches = RESULT_LINE.findall(output.replace("\r", ""))
    if len(matches) != 1:
        return None
    keys = ("policy", "cpus", "finish", "deadline", "miss")
    return dict(zip(keys, (int(value) for value in matches[0])))


def host_miss(fields):
    """Cross-check rule shared with the harness: finish > deadline."""
    return 1 if fields["finish"] > fields["deadline"] else 0


class AdaptivePlanner(Planner):
    def __init__(self, workload, audit=None):
        if set(workload) != set(WORKLOAD_KEYS) or any(
                type(workload[key]) is not int for key in WORKLOAD_KEYS):
            raise ValueError("workload must have integer %s" % ", ".join(WORKLOAD_KEYS))
        self.workload = dict(workload)
        self.audit = audit
        self.emitted = []
        self.pending = [
            {"tool": "set_policy", "args": {"policy": PILOT_POLICY}},
            {"tool": "run_pipeline", "args": dict(self.workload)},
        ]
        self.steps = []
        self.runs = {}
        self.finished = False

    def _record(self, phase, policy, fields, decision, reason):
        step = {
            "step": len(self.steps) + 1,
            "phase": phase,
            "policy": policy,
            "parsed": fields,
            "host_miss": host_miss(fields) if fields and "finish" in fields else None,
            "decision": decision,
            "reason": reason,
        }
        self.steps.append(step)
        if self.audit is not None:
            self.audit.write({"planner": "adaptive", "workload": dict(self.workload), **step})
        return step

    def _stop(self, phase, policy, fields, decision, reason):
        self._record(phase, policy, fields, decision, reason)
        self.finished = True
        self.pending = []
        return None

    def _next(self):
        if not self.pending or len(self.steps) >= MAX_STEPS:
            self.finished = True
            return None
        action = self.pending.pop(0)
        self.emitted.append(action)
        return action

    def plan(self, request, state):
        if self.finished:
            return None
        phase = "pilot" if "pilot" not in self.runs else "rerun"
        policy = PILOT_POLICY if phase == "pilot" else SWITCH_POLICY
        # AgentLoop appends only validated actions, so a shorter list means
        # the validator rejected the last proposal; retrying would loop.
        if len(state.get("actions", [])) != len(self.emitted):
            return self._stop(phase, policy, None, "abort",
                              "validator rejected the last proposed action")
        if self.emitted:
            last = self.emitted[-1]
            observation = state["observations"][-1]
            if observation["status"] != "ok":
                return self._stop(phase, policy, None, "abort",
                                  "%s returned status %s" % (last["tool"], observation["status"]))
            if last["tool"] == "run_pipeline":
                return self._after_run(phase, policy, parse_result(observation["output"]))
            if last["tool"] == "summarize":
                self.finished = True
                return None
        return self._next()

    def _after_run(self, phase, policy, fields):
        if fields is None:
            return self._stop(phase, policy, None, "abort", "no single RESULT line in output")
        # A policy number other than the one just set means schedctl did not
        # take effect, so the comparison would be meaningless.
        if fields["policy"] != POLICY_NUMBER[policy]:
            return self._stop(phase, policy, fields, "abort",
                              "RESULT policy=%d, expected %d" % (fields["policy"],
                                                                POLICY_NUMBER[policy]))
        if fields["deadline"] != self.workload["deadline"]:
            return self._stop(phase, policy, fields, "abort",
                              "RESULT deadline=%d, sent %d" % (fields["deadline"],
                                                               self.workload["deadline"]))
        if fields["miss"] != host_miss(fields):
            return self._stop(phase, policy, fields, "abort",
                              "RESULT miss=%d disagrees with finish>deadline (%d > %d)"
                              % (fields["miss"], fields["finish"], fields["deadline"]))
        self.runs[phase] = fields
        if phase == "pilot":
            if not fields["miss"]:
                return self._stop(phase, policy, fields, "stop",
                                  "pilot met the deadline (finish %d <= %d)"
                                  % (fields["finish"], fields["deadline"]))
            self._record(phase, policy, fields, "switch",
                         "pilot missed (finish %d > %d); rerun under %s"
                         % (fields["finish"], fields["deadline"], SWITCH_POLICY))
            self.pending = [
                {"tool": "set_policy", "args": {"policy": SWITCH_POLICY}},
                {"tool": "run_pipeline", "args": dict(self.workload)},
            ]
            return self._next()
        self._record(phase, policy, fields, "compare", "rerun finished")
        return self._compare()

    def _compare(self):
        pilot, rerun = self.runs["pilot"], self.runs["rerun"]
        improved = rerun["miss"] < pilot["miss"]
        # The summary is built only from parsed integers, never model text.
        text = ("adaptive: %s finish=%d miss=%d; %s finish=%d miss=%d; "
                "deadline=%d; switch %s" % (
                    PILOT_POLICY, pilot["finish"], pilot["miss"],
                    SWITCH_POLICY, rerun["finish"], rerun["miss"],
                    pilot["deadline"], "helped" if improved else "did not help"))
        self._record("compare", SWITCH_POLICY,
                     {"pilot_finish": pilot["finish"], "rerun_finish": rerun["finish"],
                      "deadline": pilot["deadline"], "finish_delta": rerun["finish"] - pilot["finish"]},
                     "done", text)
        self.pending = [{"tool": "summarize", "args": {"text": text}}]
        # The comparison is step 3; emit its summary even though the step
        # budget is now used up.
        action = self.pending.pop(0)
        self.emitted.append(action)
        return action
