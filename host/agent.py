"""Command-line entry point for the Stage 3 host agent."""

import argparse

from audit import AuditLog
from bridge.qemu_bridge import QemuBridge
from config import deadline_for_alpha, load_config, require_w_ticks
from loop import AgentLoop
from planners.adaptive import AdaptivePlanner
from planners.deterministic import DeterministicPlanner
from planners.ollama_planner import OllamaPlanner


def adaptive_workload(config, alpha, cpus):
    """The harness workload with deadline round(alpha * W) and cpus' hogs.

    Refuses (SystemExit) while W_ticks is null, before any QEMU is started.
    """
    w_ticks = require_w_ticks(config, "the adaptive agent")
    workload = {key: config["harness_workload"][key] for key in ("stages", "work", "bytes")}
    workload["deadline"] = deadline_for_alpha(alpha, w_ticks)
    workload["hogs"] = config["hogs_by_cpus"][str(cpus)]
    return workload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--planner", choices=("deterministic", "ollama", "adaptive"),
                        default="deterministic")
    parser.add_argument("--mode", choices=("normal", "injected"), default="normal")
    parser.add_argument("--alpha", type=float, default=None,
                        help="adaptive planner only: deadline = round(alpha * W) "
                             "(default: config alpha)")
    args = parser.parse_args()
    config = load_config()
    audit = AuditLog()
    if args.planner == "ollama":
        planner = OllamaPlanner()
    elif args.planner == "adaptive":
        # The bridge below starts with its default of one CPU.
        alpha = config["alpha"] if args.alpha is None else args.alpha
        planner = AdaptivePlanner(adaptive_workload(config, alpha, 1), audit)
    else:
        planner = DeterministicPlanner(args.mode)
    bridge = QemuBridge()
    bridge.start()
    try:
        state = AgentLoop(
            bridge, planner, config, audit=audit, execution_source="qemu"
        ).run(args.request)
        for observation in state["observations"]:
            print("[%s] %s" % (observation["status"], observation["tool"]))
            if observation["output"]:
                print(observation["output"], end="")
        print("Final state: %s" % state)
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
