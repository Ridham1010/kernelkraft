#!/usr/bin/env python3
"""Run the scheduler matrix and persist resumable CSV results."""

import argparse
import csv
import json
import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.config import alpha_label, deadline_for_alpha
from host.validator import ValidationError, validate_action

POLICIES = ("rr", "edf", "edf_donate")
CPUS_LIST = (1, 3)
RUNS_PER_CELL = 20
DRY_RUNS_PER_CELL = 2
# miss_kernel is appended last so older readers that index the first ten
# columns keep working.
FIELDNAMES = (
    "policy", "cpus", "run", "alpha", "finish", "deadline", "miss",
    "status", "commit_hash", "rawlog_path", "miss_kernel",
)
RESULT_REGEX = re.compile(
    r"^RESULT policy=(\d+) cpus=(\d+) finish=(\d+) "
    r"deadline=(\d+) miss=(\d+)\r?$", re.MULTILINE
)
POLICY_NUMBER = {"rr": 0, "edf": 1, "edf_donate": 2}
# The xv6 shell reads at most 99 characters per line; stay well below it.
GUEST_LINE_LIMIT = 90
# QEMUEXTRA reaches /bin/sh through the make recipe, so allow only
# characters that cannot start shell or make syntax ($ ; ` | & quotes ...).
QEMU_EXTRA_REGEX = re.compile(r"^[A-Za-z0-9 ,._=-]{0,200}$")


def log(message):
    print("[{}] {}".format(datetime.now().strftime("%H:%M:%S"), message))


def get_commit_hash(project_root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_root), capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"


def check_clean_tree(project_root, allow_dirty):
    """Abort if tracked files differ from HEAD.

    commit_hash in every row must describe the tree that produced it, so a
    batch on uncommitted changes is refused. Untracked files (raw logs,
    dist/) do not affect the build and are ignored.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=str(project_root), capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        problem = "git status failed: {}".format(result.stderr.strip())
    elif result.stdout.strip():
        problem = "working tree has uncommitted changes:\n" + result.stdout
    else:
        return
    if allow_dirty:
        log("WARNING: {} (continuing because of --allow-dirty)".format(problem))
        return
    raise SystemExit(
        "Refusing to start: {}\nCommit first so commit_hash describes the "
        "tree, or pass --allow-dirty for testing.".format(problem))


def qemu_extra_arg(config):
    """Build the single make argument QEMUEXTRA=-snapshot <qemu_extra>."""
    extra = config.get("qemu_extra", "")
    if not isinstance(extra, str) or not QEMU_EXTRA_REGEX.fullmatch(extra):
        raise ValueError(
            "config qemu_extra must be a string of letters, digits, spaces "
            "and , . _ = - (at most 200 characters)")
    extra = extra.strip()
    return "QEMUEXTRA=-snapshot" + (" " + extra if extra else "")


def parse_list(text, kind, name):
    """Parse a comma-separated CLI list such as '1.0,1.5' or '1,3'."""
    try:
        values = [kind(item) for item in text.split(",") if item.strip()]
    except ValueError:
        raise SystemExit("--{}: cannot parse {!r}".format(name, text))
    if not values:
        raise SystemExit("--{}: empty list".format(name))
    return values


def cell_workload(config, cpus, alpha):
    """Return the validated wfgen arguments for one (cpus, alpha) cell.

    The workload goes through the same validator as planner actions (with
    clamping forced off), so the harness can never send a deadline the agent
    would be refused, and an out-of-range alpha fails before QEMU starts.
    """
    deadline = deadline_for_alpha(alpha, config["W_ticks"])
    if deadline <= 0:
        raise ValueError("alpha {} gives deadline {} <= 0".format(alpha, deadline))
    workload = {
        "stages": config["harness_workload"]["stages"],
        "work": config["harness_workload"]["work"],
        "bytes": config["harness_workload"]["bytes"],
        "deadline": deadline,
        "hogs": config["hogs_by_cpus"][str(cpus)],
    }
    strict = dict(config, clamp=False)
    try:
        validate_action({"tool": "run_pipeline", "args": workload}, strict)
    except ValidationError as error:
        raise ValueError(
            "alpha {} with W={} gives deadline {}; validator allows "
            "{}..{}: {}".format(alpha, config["W_ticks"], deadline,
                                config["MIN_SLACK"], config["NO_DEADLINE"],
                                error))
    return workload


def guest_commands(policy, workload):
    """Return the fixed guest command lines, checked against the shell limit."""
    if policy not in POLICY_NUMBER:
        raise ValueError("unknown policy {!r}".format(policy))
    commands = [
        "schedctl {}".format(policy),
        "wfgen {stages} {work} {bytes} {deadline} {hogs}".format(
            **{key: int(workload[key]) for key in
               ("stages", "work", "bytes", "deadline", "hogs")}),
        "exit",
    ]
    for command in commands:
        # An explicit check, not assert, so python -O cannot remove it.
        if len(command) >= GUEST_LINE_LIMIT:
            raise ValueError("guest command too long ({} chars): {}".format(
                len(command), command))
    return commands


def rawlog_name(policy, cpus, alpha, run):
    return "{}_cpus{}_a{}_run{}.raw".format(policy, cpus, alpha_label(alpha), run)


def parse_result(output, policy, cpus, deadline=None):
    matches = RESULT_REGEX.findall(output.replace("\r", ""))
    if len(matches) != 1:
        return None
    result = tuple(int(value) for value in matches[0])
    if result[0] != POLICY_NUMBER[policy] or result[1] != cpus:
        return None
    # wfgen echoes the deadline it was given; a different value means the
    # line does not belong to the command this harness sent.
    if deadline is not None and result[3] != deadline:
        return None
    return {
        "finish": result[2],
        "deadline": result[3],
        # Host miss rule, identical for every policy. The kernel counter is
        # cumulative per boot and starts its clock at the final stage's
        # setworkflow, so it is kept only as miss_kernel.
        "miss": 1 if result[2] > result[3] else 0,
        "miss_kernel": result[4],
    }


def run_qemu(project_root, xv6_dir, qemu_bin, policy, cpus, workload,
             rawlog, timeout, qemu_extra="QEMUEXTRA=-snapshot"):
    commands = guest_commands(policy, workload)
    command = [
        "make", "-C", str(project_root / xv6_dir), "qemu-nox",
        "CPUS={}".format(cpus), qemu_extra,
    ]
    if qemu_bin:
        command.append("QEMU={}".format(qemu_bin))
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.setsid()
        except PermissionError:
            # pty.fork may already make the child a session leader.
            pass
        os.execvpe(command[0], command, os.environ.copy())

    output = []
    command_index = 0
    started = time.monotonic()
    result_seen = False
    try:
        while time.monotonic() - started < timeout:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue
            data = os.read(fd, 4096)
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            output.append(text)
            last_line = "".join(output).splitlines()[-1] if output else ""
            if last_line.endswith("$ ") and command_index < len(commands):
                line = commands[command_index]
                if len(line) >= GUEST_LINE_LIMIT:
                    raise ValueError("guest command too long: " + line)
                os.write(fd, (line + "\n").encode())
                command_index += 1
            if RESULT_REGEX.search("".join(output).replace("\r", "")):
                result_seen = True
                break
    except (OSError, ValueError):
        pass
    finally:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

    text = "".join(output)
    rawlog.write_text(text, encoding="utf-8")
    if result_seen:
        return text, "success"
    if "panic" in text.lower():
        return text, "panic"
    if time.monotonic() - started >= timeout:
        return text, "timeout"
    return text, "no_result"


def result_row(policy, cpus, run, alpha, commit_hash, rawlog, result, status):
    return {
        "policy": policy,
        "cpus": cpus,
        "run": run,
        "alpha": alpha,
        "finish": "" if result is None else result["finish"],
        "deadline": "" if result is None else result["deadline"],
        "miss": "" if result is None else result["miss"],
        "status": status,
        "commit_hash": commit_hash,
        "rawlog_path": str(rawlog),
        "miss_kernel": "" if result is None else result["miss_kernel"],
    }


def check_csv_header(csv_path):
    """Refuse to append to a CSV written with a different column set."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return False
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        header = next(csv.reader(csv_file), [])
    if tuple(header) != FIELDNAMES:
        raise SystemExit(
            "Refusing to append to {}: its header {} differs from {}. "
            "Use a new --output file.".format(csv_path, header, list(FIELDNAMES)))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="run two runs per cell (overrides --runs)")
    parser.add_argument("--runs", type=int, default=None,
                        help="runs per cell (default {})".format(RUNS_PER_CELL))
    parser.add_argument("--alphas", default=None,
                        help="comma-separated alphas (default: config alpha)")
    parser.add_argument("--cpus", default=None,
                        help="comma-separated CPU counts (default: config cpus_allowed)")
    parser.add_argument("--resume", action="store_true",
                        help="skip rows already present in the output CSV")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="run even if tracked files are modified (testing only)")
    parser.add_argument("--output", default="results.csv")
    parser.add_argument("--rawlog-dir", default="logs/harness")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--config", default="host/config.json")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    config_path = project_root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    qemu_bin = config.get("qemu_bin")
    xv6_dir = config["xv6_dir"]

    if args.runs is not None and args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.dry_run:
        runs = DRY_RUNS_PER_CELL
    elif args.runs is not None:
        runs = args.runs
    else:
        runs = RUNS_PER_CELL
    alphas = (parse_list(args.alphas, float, "alphas") if args.alphas
              else [float(config["alpha"])])
    cpus_list = (parse_list(args.cpus, int, "cpus") if args.cpus
                 else list(config["cpus_allowed"]))
    policies = list(POLICIES)

    # Validate every cell before the first QEMU launch so a bad flag fails
    # immediately instead of hours into a batch.
    for cpus in cpus_list:
        if cpus not in config["cpus_allowed"]:
            raise SystemExit("cpus {} is not in config cpus_allowed".format(cpus))
    workloads = {}
    try:
        qemu_extra = qemu_extra_arg(config)
        for alpha in alphas:
            for cpus in cpus_list:
                workloads[(cpus, alpha)] = cell_workload(config, cpus, alpha)
                for policy in policies:
                    guest_commands(policy, workloads[(cpus, alpha)])
    except (KeyError, ValueError) as error:
        raise SystemExit("Invalid configuration: {}".format(error))

    check_clean_tree(project_root, args.allow_dirty)
    commit_hash = get_commit_hash(project_root)
    rawlog_dir = project_root / args.rawlog_dir
    rawlog_dir.mkdir(parents=True, exist_ok=True)
    csv_path = project_root / args.output
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = check_csv_header(csv_path)

    completed = set()
    if args.resume and file_exists:
        with csv_path.open(newline="", encoding="utf-8") as csv_file:
            for row in csv.DictReader(csv_file):
                if row.get("status") == "success":
                    completed.add((row["policy"], int(row["cpus"]),
                                   alpha_label(row["alpha"]), int(row["run"])))

    log("{} alpha(s) x {} policies x {} CPU count(s) x {} runs; {}".format(
        len(alphas), len(policies), len(cpus_list), runs, qemu_extra))
    with csv_path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for alpha in alphas:
            label = alpha_label(alpha)
            for policy in policies:
                for cpus in cpus_list:
                    workload = workloads[(cpus, alpha)]
                    for run in range(1, runs + 1):
                        key = (policy, cpus, label, run)
                        if args.resume and key in completed:
                            log("Skipping completed {}".format(key))
                            continue
                        rawlog = rawlog_dir / rawlog_name(policy, cpus, alpha, run)
                        log("Running policy={} cpus={} alpha={} deadline={} "
                            "run={}/{}".format(policy, cpus, label,
                                               workload["deadline"], run, runs))
                        try:
                            output, status = run_qemu(
                                project_root, xv6_dir, qemu_bin, policy, cpus,
                                workload, rawlog, args.timeout, qemu_extra)
                            result = parse_result(output, policy, cpus,
                                                  workload["deadline"])
                            if status == "success" and result is None:
                                status = "no_result"
                        except (OSError, subprocess.SubprocessError) as error:
                            log("Run failed: {}".format(error))
                            result = None
                            status = "error"
                            rawlog.write_text("", encoding="utf-8")
                        try:
                            rawlog_path = rawlog.relative_to(project_root)
                        except ValueError:
                            rawlog_path = rawlog
                        writer.writerow(result_row(
                            policy, cpus, run, label, commit_hash,
                            rawlog_path, result, status))
                        csv_file.flush()


if __name__ == "__main__":
    main()
