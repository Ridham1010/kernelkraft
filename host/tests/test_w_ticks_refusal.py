"""W_ticks is null until recalibration: the adaptive agent must refuse."""

import importlib
import sys
from pathlib import Path

import pytest

from host.config import load_config, require_w_ticks

HOST = Path(__file__).resolve().parents[1]


def test_require_w_ticks():
    with pytest.raises(SystemExit) as excinfo:
        require_w_ticks({"W_ticks": None}, "the test")
    assert "W_ticks is null" in str(excinfo.value)
    assert "the test" in str(excinfo.value)
    with pytest.raises(SystemExit):
        require_w_ticks({}, "the test")
    assert require_w_ticks({"W_ticks": 24.4}, "the test") == 24.4


@pytest.fixture
def agent(monkeypatch):
    # agent.py uses top-level imports (run as `python host/agent.py`).
    monkeypatch.syspath_prepend(str(HOST))
    for name in ("agent", "config"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module("agent")


def test_adaptive_agent_refuses_null_w_ticks(agent):
    config = load_config()
    assert config["W_ticks"] is None
    with pytest.raises(SystemExit) as excinfo:
        agent.adaptive_workload(config, 1.5, 1)
    assert "W_ticks is null" in str(excinfo.value)
    assert "adaptive agent" in str(excinfo.value)


def test_adaptive_workload_with_w_ticks(agent):
    config = dict(load_config(), W_ticks=24.4)
    assert agent.adaptive_workload(config, 1.5, 1) == {
        "stages": 4, "work": 100, "bytes": 2048, "deadline": 37,
        "hogs": config["hogs_by_cpus"]["1"]}
