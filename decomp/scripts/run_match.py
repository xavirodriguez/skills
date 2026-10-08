#!/usr/bin/env python3
"""Controlled build/compare harness with a machine-readable experiment ledger."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from parse_compare import parse_compare


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
    configured = os.environ.get("DECOMP_SHELL")
    if configured in {"powershell", "pwsh", "bash", "cmd"}:
        return configured
    return "powershell" if os.name == "nt" else "bash"


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


def run_compare(command: str, root: Path, shell: str, path: Path) -> tuple[int, str, dict]:
    code, log = run(command, root, shell)
    path.write_text(log, encoding="utf-8")
    return code, log, parse_compare(log)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--target", required=True)
    parser.add_argument("--build-command")
    parser.add_argument("--compare-command")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--shell", choices=("auto", "powershell", "pwsh", "bash", "cmd"), default="auto")
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--source-change", default="")
    parser.add_argument("--compare-before", action="store_true")
    parser.add_argument("--compare-on-build-failure", action="store_true")
    parser.add_argument(
        "--allow-build-failure-if-compare-passes",
        action="store_true",
        help="Return success when build exits non-zero but the authoritative compare passes.",
    )
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

    if not args.build_command or not args.compare_command:
        print(json.dumps({
            "status": "plan-only",
            "message": "Supply explicit authoritative build and compare commands.",
            "target": args.target,
            "state": str(state),
        }, indent=2))
        return 0

    config = {
        "project": str(root),
        "target": args.target,
        "build_command": args.build_command,
        "compare_command": args.compare_command,
        "shell": shell,
        "iterations": args.iterations,
        "hypothesis": args.hypothesis,
        "source_change": args.source_change,
        "compare_before": args.compare_before,
        "compare_on_build_failure": args.compare_on_build_failure,
        "allow_build_failure_if_compare_passes": args.allow_build_failure_if_compare_passes,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (state / "run.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if args.dry_run:
        print(json.dumps({"status": "dry-run", **config}, indent=2, sort_keys=True))
        return 0

    if not args.force:
        print("Refusing to execute without --force. Use --dry-run for planning.", flush=True)
        return 2

    ledger = state / "hypotheses.jsonl"

    for iteration in range(1, args.iterations + 1):
        before = {}
        if args.compare_before:
            before_code, _, before = run_compare(
                args.compare_command,
                root,
                shell,
                target_state / f"iteration-{iteration:03d}-compare-before.log",
            )
            before["exit_code"] = before_code

        build_code, build_log = run(args.build_command, root, shell)
        (target_state / f"iteration-{iteration:03d}-build.log").write_text(
            build_log,
            encoding="utf-8",
        )

        after = {}
        compare_code = None
        if build_code == 0 or args.compare_on_build_failure:
            compare_code, _, after = run_compare(
                args.compare_command,
                root,
                shell,
                target_state / f"iteration-{iteration:03d}-compare.log",
            )

        decision = "build-failed"
        if compare_code is not None and compare_code == 0:
            if after.get("exact_match"):
                if build_code == 0:
                    decision = "exact-match"
                elif args.allow_build_failure_if_compare_passes:
                    decision = "exact-match-build-failed-allowed"
                else:
                    decision = "exact-match-build-failed"
            else:
                decision = "compare-ran"
        elif build_code == 0 and compare_code not in (None, 0):
            decision = "compare-failed"

        append_jsonl(ledger, {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "iteration": iteration,
            "target": args.target,
            "hypothesis": args.hypothesis,
            "source_change": args.source_change,
            "build_exit": build_code,
            "compare_exit": compare_code,
            "match_before": before.get("match_percent"),
            "match_after": after.get("match_percent"),
            "first_mismatch_before": before.get("first_mismatch"),
            "first_mismatch_after": after.get("first_mismatch"),
            "exact_match_after": after.get("exact_match"),
            "decision": decision,
        })

        if build_code != 0:
            if (
                args.allow_build_failure_if_compare_passes
                and compare_code == 0
                and after.get("exact_match")
            ):
                continue
            if not args.compare_on_build_failure:
                return 1
            if compare_code != 0:
                return 1
            # Compare ran but the build did not complete and the result did not
            # satisfy the explicit allow policy.
            return 1

        if compare_code != 0:
            return 1

    print(json.dumps({
        "status": "completed",
        "target": args.target,
        "iterations": args.iterations,
        "state": str(state),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
