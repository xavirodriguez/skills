#!/usr/bin/env python3
"""Safe orchestration harness for matching-decomp experiments.

It never guesses project commands and never edits source. The LLM agent remains
responsible for interpreting Ghidra evidence and proposing source changes.
Commands run through an explicit shell so Windows PowerShell does not silently
fall back to cmd.exe while the outer agent uses PowerShell syntax.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

def build_process_args(command: str, shell: str) -> list[str]:
    if shell == "powershell":
        return ["powershell.exe", "-NoProfile", "-Command", command]
    if shell == "pwsh":
        return ["pwsh", "-NoProfile", "-Command", command]
    if shell == "bash":
        return ["bash", "-lc", command]
    if shell == "cmd":
        return ["cmd.exe", "/d", "/s", "/c", command]
    raise ValueError(f"Unsupported shell: {shell}")


def detect_shell() -> str:
    if os.name != "nt":
        return "bash"
    return "pwsh" if shutil.which("pwsh") else "powershell"


def run(command: str, cwd: Path, shell: str) -> tuple[int, str]:
    started = time.time()
    process = subprocess.run(
        build_process_args(command, shell),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed = round(time.time() - started, 3)
    return process.returncode, (
        f"$ [{shell}] {command}\n\n{process.stdout}\n\n"
        f"[exit={process.returncode}, seconds={elapsed}]\n"
    )

def append_jsonl(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--target", required=True)
    parser.add_argument("--build-command")
    parser.add_argument("--compare-command")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shell", choices=("auto", "powershell", "pwsh", "bash", "cmd"), default="auto")
    parser.add_argument("--force", action="store_true", help="Allow command execution.")
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.dry_run and args.force:
        parser.error("--dry-run and --force are mutually exclusive")

    shell = detect_shell() if args.shell == "auto" else args.shell

    root = Path(args.project).resolve()
    state = root / ".decomp-agent"
    target_state = state / "targets" / args.target.replace("/", "_")
    target_state.mkdir(parents=True, exist_ok=True)

    config = {
        "project": str(root),
        "target": args.target,
        "build_command": args.build_command,
        "compare_command": args.compare_command,
        "shell": shell,
        "iterations": args.iterations,
        "dry_run": args.dry_run,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (state / "run.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.build_command or not args.compare_command:
        print(json.dumps({
            "status": "plan-only",
            "message": "Supply the project's authoritative build and compare commands; commands are never guessed.",
            "target": args.target,
            "state": str(state),
        }, indent=2))
        return 0

    if args.dry_run:
        print(json.dumps({
            "status": "dry-run",
            "target": args.target,
            "build_command": args.build_command,
            "compare_command": args.compare_command,
            "shell": shell,
            "iterations": args.iterations,
            "message": "No command executed and no source modified.",
        }, indent=2))
        return 0

    if not args.force:
        print("Refusing to execute without --force. Use --dry-run for planning.", flush=True)
        return 2

    ledger = state / "hypotheses.jsonl"
    for iteration in range(1, args.iterations + 1):
        build_code, build_log = run(args.build_command, root, shell)
        (target_state / f"iteration-{iteration:03d}-build.log").write_text(build_log, encoding="utf-8")
        compare_code, compare_log = (0, "")
        if build_code == 0:
            compare_code, compare_log = run(args.compare_command, root, shell)
            (target_state / f"iteration-{iteration:03d}-compare.log").write_text(compare_log, encoding="utf-8")

        append_jsonl(ledger, {
            "iteration": iteration,
            "target": args.target,
            "build_exit": build_code,
            "compare_exit": compare_code,
            "decision": "build-failed" if build_code else ("compare-failed" if compare_code else "compare-ran"),
        })
        if build_code != 0 or compare_code != 0:
            return 1

    print(json.dumps({
        "status": "completed",
        "target": args.target,
        "iterations": args.iterations,
        "state": str(state),
        "message": "Build/compare orchestration completed. The harness does not interpret semantics or edit source.",
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
