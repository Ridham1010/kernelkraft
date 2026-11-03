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
import time
from datetime import datetime
from pathlib import Path

POLICIES = ("rr", "edf", "edf_donate")
CPUS_LIST = (1, 3)
RUNS_PER_CELL = 20
DRY_RUNS_PER_CELL = 2
FIELDNAMES = (
    "policy", "cpus", "run", "alpha", "finish", "deadline", "miss",
    "status", "commit_hash", "rawlog_path",
)
RESULT_REGEX = re.compile(
    r"^RESULT policy=(\d+) cpus=(\d+) finish=(\d+) "
    r"deadline=(\d+) miss=(\d+)\r?$", re.MULTILINE
)
POLICY_NUMBER = {"rr": 0, "edf": 1, "edf_donate": 2}


def log(message):
    print("[{}] {}".format(datetime.now().strftime("%H:%M:%S"), message))


def get_commit_hash(project_root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_root), capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"


def parse_result(output, policy, cpus):
    matches = RESULT_REGEX.findall(output.replace("\r", ""))
    if len(matches) != 1:
        return None
    result = tuple(int(value) for value in matches[0])
    if result[0] != POLICY_NUMBER[policy] or result[1] != cpus:
        return None
    return {"finish": result[2], "deadline": result[3], "miss": result[4]}


def run_qemu(project_root, xv6_dir, qemu_bin, policy, cpus, workload,
             rawlog, timeout):
    command = [
        "make", "-C", str(project_root / xv6_dir), "qemu-nox",
        "CPUS={}".format(cpus), "QEMUEXTRA=-snapshot",
    ]
    if qemu_bin:
        command.append("QEMU={}".format(qemu_bin))
    guest_commands = [
        "schedctl {}".format(policy),
        "wfgen {stages} {work} {bytes} {deadline} {hogs}".format(**workload),
        "exit",
    ]
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
            if last_line.endswith("$ ") and command_index < len(guest_commands):
                os.write(fd, (guest_commands[command_index] + "\n").encode())
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
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="run two runs per policy/CPU cell")
    parser.add_argument("--resume", action="store_true",
                        help="skip rows already present in the output CSV")
    parser.add_argument("--output", default="results.csv")
    parser.add_argument("--rawlog-dir", default="logs/harness")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--config", default="host/config.json")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    config_path = project_root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    workload = config["harness_workload"].copy()
    alpha = str(config["alpha"])
    rawlog_dir = project_root / args.rawlog_dir
    rawlog_dir.mkdir(parents=True, exist_ok=True)
    csv_path = project_root / args.output
    qemu_bin = config.get("qemu_bin")
    xv6_dir = config["xv6_dir"]
    cpus_list = tuple(config["cpus_allowed"])
    commit_hash = get_commit_hash(project_root)
    runs = DRY_RUNS_PER_CELL if args.dry_run else RUNS_PER_CELL

    completed = set()
    if args.resume and csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as csv_file:
            for row in csv.DictReader(csv_file):
                if row.get("status") == "success":
                    completed.add((row["policy"], int(row["cpus"]), int(row["run"])))

    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for policy in POLICIES:
            for cpus in cpus_list:
                for run in range(1, runs + 1):
                    key = (policy, cpus, run)
                    if args.resume and key in completed:
                        log("Skipping completed {}".format(key))
                        continue
                    rawlog = rawlog_dir / "{}_cpus{}_run{}.raw".format(policy, cpus, run)
                    log("Running policy={} cpus={} run={}/{}".format(
                        policy, cpus, run, runs))
                    try:
                        cell_workload = workload.copy()
                        cell_workload["hogs"] = config["hogs_by_cpus"][str(cpus)]
                        output, status = run_qemu(
                            project_root, xv6_dir, qemu_bin, policy, cpus,
                            cell_workload,
                            rawlog, args.timeout)
                        result = parse_result(output, policy, cpus)
                        if status == "success" and result is None:
                            status = "no_result"
                    except (OSError, subprocess.SubprocessError, KeyError) as error:
                        log("Run failed: {}".format(error))
                        result = None
                        status = "error"
                        rawlog.write_text("", encoding="utf-8")
                    try:
                        rawlog_path = rawlog.relative_to(project_root)
                    except ValueError:
                        rawlog_path = rawlog
                    writer.writerow(result_row(
                        policy, cpus, run, alpha, commit_hash,
                        rawlog_path, result, status))
                    csv_file.flush()


if __name__ == "__main__":
    main()
