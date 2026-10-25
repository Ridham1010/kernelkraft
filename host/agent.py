"""Command-line entry point for the Stage 3 host agent."""

import argparse

from bridge.qemu_bridge import QemuBridge
from config import load_config
from loop import AgentLoop
from planners.deterministic import DeterministicPlanner
from planners.ollama_planner import OllamaPlanner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--planner", choices=("deterministic", "ollama"), default="deterministic")
    parser.add_argument("--mode", choices=("normal", "injected"), default="normal")
    args = parser.parse_args()
    planner = (
        OllamaPlanner() if args.planner == "ollama" else DeterministicPlanner(args.mode)
    )
    bridge = QemuBridge()
    bridge.start()
    try:
        state = AgentLoop(
            bridge, planner, load_config(), execution_source="qemu"
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
