"""Closed-loop plan, validate, execute, observe orchestration."""

try:
    from host.audit import AuditLog, kernel_log_lines
    from host.tools import TOOLS
    from host.validator import ValidationError, validate_action
except ImportError:
    from audit import AuditLog, kernel_log_lines
    from tools import TOOLS
    from validator import ValidationError, validate_action


def _result_fields(output):
    fields = {}
    for token in output.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in ("policy", "cpus", "finish", "deadline", "miss"):
            try:
                fields[key] = int(value)
            except ValueError:
                return None
    return fields if len(fields) == 5 else None


class AgentLoop:
    def __init__(self, bridge, planner, config=None, audit=None, max_steps=8, execution_source="unknown"):
        self.bridge = bridge
        self.planner = planner
        self.config = config
        self.audit = audit or AuditLog()
        self.max_steps = max_steps
        self.execution_source = execution_source

    def run(self, request):
        state = {"actions": [], "observations": [], "read_paths": [], "injected": False}
        for _ in range(self.max_steps):
            proposed = self.planner.plan(request, state)
            if proposed is None:
                break
            try:
                validated = validate_action(proposed, self.config)
            except ValidationError as error:
                if proposed.get("tool") == "run_pipeline":
                    state["injected"] = True
                self.audit.write({
                    "user_request": request,
                    "proposed_call": proposed,
                    "validated_call": None,
                    "validation_error": str(error),
                    "guest_output": "",
                    "observation_status": "rejected",
                    "kernel_log_lines": [],
                    "final_state": dict(state),
                    "execution_source": self.execution_source,
                })
                continue
            spec = TOOLS[validated["tool"]]
            if spec["host_only"]:
                output = validated["args"].get("text", "")
                status = "ok"
                observation = None
            else:
                observation = self.bridge.run(spec["build"](validated["args"]))
                output = observation.output
                status = observation.status
                if validated["tool"] == "read_file" and output.startswith("cat: "):
                    status = "error"
            state["actions"].append(validated)
            if validated["tool"] == "read_file":
                state["read_paths"].append(validated["args"]["path"])
            observation_record = {
                "tool": validated["tool"],
                "status": status,
                "output": output,
            }
            if output.startswith("RESULT "):
                result = _result_fields(output)
                if result is not None:
                    observation_record["result"] = result
            state["observations"].append(observation_record)
            self.audit.write({
                "user_request": request,
                "proposed_call": proposed,
                "validated_call": validated,
                "validation_error": None,
                "guest_output": output,
                "observation_status": status,
                "kernel_log_lines": kernel_log_lines(output),
                "final_state": dict(state),
                "execution_source": self.execution_source,
            })
            if observation is not None and status in ("panic", "timeout"):
                break
        return state
