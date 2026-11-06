"""Stage 7 harness tests (no QEMU, git is mocked)."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

from host.config import deadline_for_alpha, load_config
from harness import run_all

ROOT = Path(__file__).resolve().parents[2]
# W_ticks is null in the real config until recalibration; tests that need a
# deadline use this value (the v1 calibration) and say so.
TEST_W = 24.4


def _config(**overrides):
    config = load_config()
    config["W_ticks"] = TEST_W
    config.update(overrides)
    return config


@pytest.mark.parametrize("alpha, expected", [
    (1.0, 24), (1.25, 31), (1.5, 37), (2.0, 49), (2.5, 61), (3.0, 73),
])
def test_deadline_is_round_alpha_times_w(alpha, expected):
    assert deadline_for_alpha(alpha, 24.4) == expected


def test_cell_workload_uses_config():
    config = _config()
    workload = run_all.cell_workload(config, 1, 1.5)
    assert workload == {"stages": 4, "work": 100, "bytes": 2048,
                        "deadline": 37, "hogs": config["hogs_by_cpus"]["1"]}


@pytest.mark.parametrize("alpha", [0.0, -1.0, 0.5, 1e12])
def test_out_of_range_alpha_rejected(alpha):
    # 0.5 * 24.4 rounds to 12 < MIN_SLACK; 1e12 exceeds NO_DEADLINE.
    with pytest.raises(ValueError):
        run_all.cell_workload(_config(), 1, alpha)


def test_rawlog_name_includes_alpha():
    assert run_all.rawlog_name("edf", 1, 1.5, 3) == "edf_cpus1_a1.5_run3.raw"
    assert run_all.rawlog_name("rr", 3, 1.25, 1) != run_all.rawlog_name("rr", 3, 1.5, 1)


def test_config_matches_plan():
    config = load_config()
    assert config["alpha_values"] == [1.2, 1.5, 2.0, 3.0]
    assert config["alpha"] == 1.5
    assert config["W_ticks"] is None
    assert config["MIN_PIPELINE_BYTES"] == 2048
    assert config["harness_workload"]["bytes"] >= config["MIN_PIPELINE_BYTES"]
    assert tuple(run_all.FIELDNAMES) == (
        "policy", "cpus", "run", "alpha", "finish", "deadline", "miss",
        "status", "commit_hash", "rawlog_path")


def test_guest_commands_below_limit():
    config = _config()
    for alpha in config["alpha_values"]:
        for cpus in config["cpus_allowed"]:
            workload = run_all.cell_workload(config, cpus, alpha)
            for policy in run_all.POLICIES:
                for line in run_all.guest_commands(policy, workload):
                    assert len(line) < run_all.GUEST_LINE_LIMIT


def test_guest_command_too_long_raises():
    workload = {"stages": 4, "work": 10 ** 40, "bytes": 10 ** 40,
                "deadline": 10 ** 9, "hogs": 3}
    with pytest.raises(ValueError):
        run_all.guest_commands("edf", workload)


def test_qemu_extra_arg_is_one_argument_and_validated():
    assert (run_all.qemu_extra_arg({"qemu_extra": "-machine pc-i440fx-yakkety"})
            == "QEMUEXTRA=-snapshot -machine pc-i440fx-yakkety")
    assert run_all.qemu_extra_arg({}) == "QEMUEXTRA=-snapshot"
    for bad in ("-machine x; rm -rf /", "$(id)", "a`b`", 5):
        with pytest.raises(ValueError):
            run_all.qemu_extra_arg({"qemu_extra": bad})


def test_parse_result_takes_miss_from_result_line():
    out = "RESULT policy=1 cpus=1 finish=40 deadline=37 miss=1\r\n"
    result = run_all.parse_result(out, "edf", 1, 37)
    assert result == {"finish": 40, "deadline": 37, "miss": 1}
    assert run_all.miss_consistent(result)
    out = "RESULT policy=1 cpus=1 finish=37 deadline=37 miss=0\n"
    assert run_all.miss_consistent(run_all.parse_result(out, "edf", 1, 37))
    assert run_all.parse_result(out, "edf", 1, 49) is None
    # A miss field that disagrees with finish > deadline is parsed as-is and
    # flagged by miss_consistent; main() turns it into bad_result.
    out = "RESULT policy=1 cpus=1 finish=37 deadline=37 miss=1\n"
    assert not run_all.miss_consistent(run_all.parse_result(out, "edf", 1, 37))


def _fake_git(porcelain):
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args, 0, porcelain, "")
        if args[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args, 0, "abcdef1234567890\n", "")
        raise AssertionError("unexpected command {}".format(args))
    return fake_run


def test_dirty_tree_aborts(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(" M host/config.json\n"))
    with pytest.raises(SystemExit) as excinfo:
        run_all.check_clean_tree(tmp_path, allow_dirty=False)
    assert "uncommitted" in str(excinfo.value)
    run_all.check_clean_tree(tmp_path, allow_dirty=True)


def test_clean_tree_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    run_all.check_clean_tree(tmp_path, allow_dirty=False)


def _project(tmp_path, config=None):
    (tmp_path / "host").mkdir()
    (tmp_path / "host" / "config.json").write_text(
        json.dumps(_config() if config is None else config), encoding="utf-8")
    return tmp_path


def _no_qemu(monkeypatch):
    monkeypatch.setattr(run_all, "run_qemu",
                        lambda *a, **k: pytest.fail("QEMU must not start"))


def test_main_refuses_null_w_ticks(monkeypatch, tmp_path):
    # The real config (W_ticks null) must stop before git or QEMU.
    project = _project(tmp_path, load_config())
    monkeypatch.setattr(run_all.subprocess, "run",
                        lambda *a, **k: pytest.fail("git must not run"))
    _no_qemu(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        run_all.main(["--project-root", str(project), "--output", "r.csv"])
    assert "W_ticks is null" in str(excinfo.value)
    assert not (project / "r.csv").exists()


@pytest.mark.parametrize("config_bytes", [1024, 2047])
def test_main_refuses_bytes_below_min_pipeline_bytes(monkeypatch, tmp_path, config_bytes):
    config = _config()
    config["harness_workload"] = dict(config["harness_workload"], bytes=config_bytes)
    project = _project(tmp_path, config)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    _no_qemu(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        run_all.main(["--project-root", str(project), "--output", "r.csv"])
    assert "MIN_PIPELINE_BYTES" in str(excinfo.value)
    assert not (project / "r.csv").exists()


def test_main_refuses_missing_min_pipeline_bytes(monkeypatch, tmp_path):
    config = _config()
    del config["MIN_PIPELINE_BYTES"]
    project = _project(tmp_path, config)
    _no_qemu(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        run_all.main(["--project-root", str(project), "--output", "r.csv"])
    assert "MIN_PIPELINE_BYTES" in str(excinfo.value)


def test_main_dirty_tree_never_launches_qemu(monkeypatch, tmp_path):
    project = _project(tmp_path)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(" M x\n"))
    monkeypatch.setattr(run_all, "run_qemu",
                        lambda *a, **k: pytest.fail("QEMU must not start"))
    with pytest.raises(SystemExit):
        run_all.main(["--project-root", str(project), "--output", "out/r.csv"])
    assert not (project / "out" / "r.csv").exists()


def test_main_writes_ok_rows_with_alpha(monkeypatch, tmp_path):
    project = _project(tmp_path)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    calls = []

    def fake_qemu(root, xv6, qemu_bin, policy, cpus, workload, rawlog, timeout,
                  qemu_extra):
        calls.append((policy, cpus, workload["deadline"], rawlog.name, qemu_extra))
        rawlog.write_text("fake", encoding="utf-8")
        text = "RESULT policy={} cpus={} finish=40 deadline={} miss={}\n".format(
            run_all.POLICY_NUMBER[policy], cpus, workload["deadline"],
            1 if 40 > workload["deadline"] else 0)
        return text, "ok"

    monkeypatch.setattr(run_all, "run_qemu", fake_qemu)
    args = ["--project-root", str(project), "--output", "new/dir/r.csv",
            "--rawlog-dir", "logs/t", "--runs", "1", "--alphas", "1.5,3.0",
            "--cpus", "1"]
    run_all.main(args)
    with (project / "new" / "dir" / "r.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == run_all.FIELDNAMES
    assert len(rows) == 6
    by_alpha = {(r["policy"], r["alpha"]): r for r in rows}
    assert by_alpha[("edf", "1.5")]["miss"] == "1"      # 40 > 37
    assert by_alpha[("edf", "3.0")]["miss"] == "0"      # 40 <= 73
    assert {r["status"] for r in rows} == {"ok"}
    assert len(rows[0]) == 10
    assert by_alpha[("rr", "3.0")]["rawlog_path"] == "logs/t/rr_cpus1_a3.0_run1.raw"
    assert len({c[3] for c in calls}) == 6
    assert calls[0][4] == "QEMUEXTRA=-snapshot -machine pc-i440fx-yakkety"

    # Resume keys include alpha: rerunning skips every completed cell.
    calls.clear()
    run_all.main(args + ["--resume"])
    assert calls == []
    # Extending to a new alpha runs only that alpha.
    run_all.main(args[:-4] + ["--alphas", "1.5,2.0", "--cpus", "1", "--resume"])
    assert {c[2] for c in calls} == {49}


def test_inconsistent_miss_is_bad_result_and_rerun_on_resume(monkeypatch, tmp_path):
    project = _project(tmp_path)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    calls = []
    lie = {"value": True}

    def fake_qemu(root, xv6, qemu_bin, policy, cpus, workload, rawlog, timeout,
                  qemu_extra):
        calls.append((policy, rawlog.name))
        rawlog.write_text("fake", encoding="utf-8")
        # finish 40 > deadline 37, so miss must be 1; edf "lies" with 0.
        miss = 0 if policy == "edf" and lie["value"] else 1
        text = "RESULT policy={} cpus={} finish=40 deadline={} miss={}\n".format(
            run_all.POLICY_NUMBER[policy], cpus, workload["deadline"], miss)
        return text, "ok"

    monkeypatch.setattr(run_all, "run_qemu", fake_qemu)
    args = ["--project-root", str(project), "--output", "r.csv",
            "--rawlog-dir", "logs/t", "--runs", "1", "--alphas", "1.5", "--cpus", "1"]
    run_all.main(args)
    with (project / "r.csv").open(newline="") as handle:
        rows = {r["policy"]: r for r in csv.DictReader(handle)}
    assert rows["edf"]["status"] == "bad_result"
    assert (rows["edf"]["finish"], rows["edf"]["miss"]) == ("40", "0")
    assert rows["rr"]["status"] == rows["edf_donate"]["status"] == "ok"

    # --resume skips only ok rows, so only the bad_result cell runs again.
    calls.clear()
    lie["value"] = False
    run_all.main(args + ["--resume"])
    assert calls == [("edf", "edf_cpus1_a1.5_run1.raw")]


def test_resume_does_not_skip_legacy_success_rows(monkeypatch, tmp_path):
    project = _project(tmp_path)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    out = project / "r.csv"
    out.write_text(",".join(run_all.FIELDNAMES) + "\n"
                   "rr,1,1,1.5,40,37,1,success,x,logs/t/a.raw\n", encoding="utf-8")
    calls = []

    def fake_qemu(root, xv6, qemu_bin, policy, cpus, workload, rawlog, timeout,
                  qemu_extra):
        calls.append(policy)
        return "", "timeout"

    monkeypatch.setattr(run_all, "run_qemu", fake_qemu)
    run_all.main(["--project-root", str(project), "--output", "r.csv",
                  "--rawlog-dir", "logs/t", "--runs", "1", "--alphas", "1.5",
                  "--cpus", "1", "--resume"])
    assert "rr" in calls


def test_main_refuses_csv_with_old_header(monkeypatch, tmp_path):
    project = _project(tmp_path)
    monkeypatch.setattr(run_all.subprocess, "run", _fake_git(""))
    _no_qemu(monkeypatch)
    old = project / "old.csv"
    # The v1 batch header: the ten columns plus miss_kernel.
    old.write_text(",".join(run_all.FIELDNAMES + ("miss_kernel",)) + "\n",
                   encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        run_all.main(["--project-root", str(project), "--output", "old.csv"])
    assert "header" in str(excinfo.value)
