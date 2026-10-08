#!/usr/bin/env python3
"""Controlled build/compare harness with policy, state and hypothesis telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from hypothesis_knowledge import compact as compact_knowledge
from hypothesis_knowledge import read_entries, search
from parse_compare import parse_compare
from session_policy import load_policy, require_allowed


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


def decode_timeout_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def run(
    command: str,
    cwd: Path,
    shell: str,
    timeout: float,
) -> tuple[int, str, float, bool]:
    started = time.perf_counter()
    try:
        process = subprocess.run(
            build_process_args(command, shell),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.perf_counter() - started, 3)
        output = decode_timeout_output(exc.stdout)
        return 124, (
            f"$ [{shell}] {command}\n\n{output}\n\n"
            f"[timeout={timeout}, exit=124, seconds={elapsed}]\n"
        ), elapsed, True

    elapsed = round(time.perf_counter() - started, 3)
    return process.returncode, (
        f"$ [{shell}] {command}\n\n{process.stdout}\n\n"
        f"[exit={process.returncode}, seconds={elapsed}]\n"
    ), elapsed, False


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def run_compare(
    command: str,
    root: Path,
    shell: str,
    path: Path,
    timeout: float,
) -> tuple[int, str, dict[str, Any], float, bool]:
    code, log, elapsed, timed_out = run(command, root, shell, timeout)
    path.write_text(log, encoding="utf-8")
    return code, log, parse_compare(log), elapsed, timed_out


def git_run(root: Path, args: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return result.returncode, result.stdout


def filtered_status_lines(raw: str) -> list[str]:
    return [
        line
        for line in raw.splitlines()
        if line and ".decomp-agent/" not in line
    ]


def capture_git_state(root: Path) -> dict[str, Any]:
    code, _ = git_run(root, ["rev-parse", "--show-toplevel"])
    if code != 0:
        return {
            "available": False,
            "reason": "not-a-git-worktree",
            "changed_files": [],
            "dirty": False,
        }

    _, head = git_run(root, ["rev-parse", "HEAD"])
    _, status = git_run(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    _, diff_stat = git_run(
        root,
        ["diff", "--stat", "--", ".", ":(exclude).decomp-agent/**"],
    )
    _, diff_name_status = git_run(
        root,
        ["diff", "--name-status", "--", ".", ":(exclude).decomp-agent/**"],
    )
    _, diff_text = git_run(
        root,
        ["diff", "--no-ext-diff", "--unified=3", "--", ".", ":(exclude).decomp-agent/**"],
    )

    filtered_status = filtered_status_lines(status)
    return {
        "available": True,
        "head": head.strip(),
        "dirty": bool(filtered_status),
        "changed_files": filtered_status,
        "diff_stat": diff_stat.strip(),
        "diff_name_status": diff_name_status.strip().splitlines(),
        "diff_hash": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_source_diff(root: Path, path: Path) -> None:
    _, diff_text = git_run(
        root,
        ["diff", "--no-ext-diff", "--unified=3", "--", ".", ":(exclude).decomp-agent/**"],
    )
    path.write_text(diff_text, encoding="utf-8")


def derive_lesson(
    before: dict[str, Any],
    after: dict[str, Any],
    decision: str,
) -> str:
    before_match = before.get("match_percent")
    after_match = after.get("match_percent")
    tags = after.get("mismatch_tags") or before.get("mismatch_tags") or []

    if after.get("exact_match"):
        return "Exact authoritative match."
    if (
        isinstance(before_match, (int, float))
        and isinstance(after_match, (int, float))
    ):
        delta = float(after_match) - float(before_match)
        if delta > 0:
            suffix = f"; mismatch families: {', '.join(tags)}" if tags else ""
            return f"Match improved by {delta:+.2f} percentage points{suffix}."
        if delta < 0:
            return f"Match regressed by {delta:+.2f} percentage points."
    if tags:
        return f"{decision}; mismatch families: {', '.join(tags)}."
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--target", required=True)
    parser.add_argument("--build-command")
    parser.add_argument("--compare-command")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--shell",
        choices=("auto", "powershell", "pwsh", "bash", "cmd"),
        default="auto",
    )
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--source-change", default="")
    parser.add_argument("--compare-before", action="store_true")
    parser.add_argument("--compare-on-build-failure", action="store_true")
    parser.add_argument(
        "--allow-build-failure-if-compare-passes",
        action="store_true",
        help="Return success when build exits non-zero but the authoritative compare passes.",
    )
    parser.add_argument(
        "--build-timeout",
        type=float,
        default=1800,
        help="Maximum seconds for each build command.",
    )
    parser.add_argument(
        "--compare-timeout",
        type=float,
        default=180,
        help="Maximum seconds for each compare command.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
        help="Session policy JSON; missing policy means no additional restriction.",
    )
    parser.add_argument(
        "--knowledge-top",
        type=int,
        default=5,
        help="Number of prior hypothesis lessons to surface.",
    )
    parser.add_argument(
        "--knowledge-query",
        default="",
        help="Additional text used to retrieve related prior hypotheses.",
    )
    parser.add_argument(
        "--no-knowledge",
        action="store_true",
        help="Disable reuse of the global hypothesis ledger.",
    )
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.dry_run and args.force:
        parser.error("--dry-run and --force are mutually exclusive")
    if args.build_timeout <= 0 or args.compare_timeout <= 0:
        parser.error("timeouts must be > 0")
    if args.knowledge_top < 0:
        parser.error("--knowledge-top must be >= 0")

    shell = detect_shell() if args.shell == "auto" else args.shell
    root = Path(args.project).resolve()
    state = root / ".decomp-agent"
    target_state = state / "targets" / args.target.replace("/", "_")
    target_state.mkdir(parents=True, exist_ok=True)

    try:
        policy = load_policy(args.policy)
        if args.build_command:
            require_allowed(args.policy, "build")
        if args.compare_command:
            require_allowed(args.policy, "compare")
    except (OSError, ValueError, PermissionError) as exc:
        print(json.dumps({
            "status": "policy-blocked",
            "message": str(exc),
            "policy": str(args.policy),
        }, indent=2, sort_keys=True))
        return 3

    if not args.build_command or not args.compare_command:
        print(json.dumps({
            "status": "plan-only",
            "message": "Supply explicit authoritative build and compare commands.",
            "target": args.target,
            "state": str(state),
            "policy": policy,
        }, indent=2, sort_keys=True))
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
        "build_timeout": args.build_timeout,
        "compare_timeout": args.compare_timeout,
        "policy": policy,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(state / "run.json", config)

    if args.dry_run:
        print(json.dumps({"status": "dry-run", **config}, indent=2, sort_keys=True))
        return 0

    if not args.force:
        print("Refusing to execute without --force. Use --dry-run for planning.", flush=True)
        return 2

    ledger = state / "hypotheses.jsonl"
    previous_entries = read_entries(ledger)

    for iteration in range(1, args.iterations + 1):
        iteration_id = f"iteration-{iteration:03d}"
        iteration_dir = target_state
        before_state = capture_git_state(root)
        write_json(iteration_dir / f"{iteration_id}-state-before.json", before_state)

        before = {}
        before_code = None
        before_elapsed = 0.0
        before_timed_out = False
        if args.compare_before:
            before_code, _, before, before_elapsed, before_timed_out = run_compare(
                args.compare_command,
                root,
                shell,
                iteration_dir / f"{iteration_id}-compare-before.log",
                args.compare_timeout,
            )
            before["exit_code"] = before_code
            before["elapsed_seconds"] = before_elapsed
            before["timed_out"] = before_timed_out

        knowledge = []
        if not args.no_knowledge and args.knowledge_top:
            query = " ".join(
                item
                for item in (
                    args.knowledge_query,
                    args.hypothesis,
                    args.source_change,
                    args.target,
                )
                if item
            )
            knowledge = search(
                previous_entries,
                target=args.target,
                query=query,
                tags=list(before.get("mismatch_tags", [])),
                top_k=args.knowledge_top,
            )
        write_json(
            iteration_dir / f"{iteration_id}-knowledge.json",
            compact_knowledge(knowledge),
        )

        build_code, build_log, build_elapsed, build_timed_out = run(
            args.build_command,
            root,
            shell,
            args.build_timeout,
        )
        (iteration_dir / f"{iteration_id}-build.log").write_text(
            build_log,
            encoding="utf-8",
        )

        after = {}
        compare_code = None
        compare_elapsed = 0.0
        compare_timed_out = False
        if build_code == 0 or args.compare_on_build_failure:
            compare_code, _, after, compare_elapsed, compare_timed_out = run_compare(
                args.compare_command,
                root,
                shell,
                iteration_dir / f"{iteration_id}-compare.log",
                args.compare_timeout,
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

        after_state = capture_git_state(root)
        write_json(iteration_dir / f"{iteration_id}-state-after.json", after_state)
        diff_path = iteration_dir / f"{iteration_id}-source.diff"
        write_source_diff(root, diff_path)

        before_match = before.get("match_percent")
        after_match = after.get("match_percent")
        delta = None
        if isinstance(before_match, (int, float)) and isinstance(after_match, (int, float)):
            delta = round(float(after_match) - float(before_match), 4)

        lesson = derive_lesson(before, after, decision)
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "iteration": iteration,
            "target": args.target,
            "hypothesis": args.hypothesis,
            "source_change": args.source_change,
            "build_command": args.build_command,
            "compare_command": args.compare_command,
            "shell": shell,
            "policy": policy,
            "build_exit": build_code,
            "build_elapsed_seconds": build_elapsed,
            "build_timed_out": build_timed_out,
            "compare_exit": compare_code,
            "compare_elapsed_seconds": compare_elapsed,
            "compare_timed_out": compare_timed_out,
            "match_before": before_match,
            "match_after": after_match,
            "match_delta": delta,
            "first_mismatch_before": before.get("first_mismatch"),
            "first_mismatch_after": after.get("first_mismatch"),
            "mismatch_tags": after.get("mismatch_tags") or before.get("mismatch_tags", []),
            "exact_match_after": after.get("exact_match"),
            "decision": decision,
            "lesson": lesson,
            "git_before": before_state,
            "git_after": after_state,
            "source_diff_path": str(diff_path.relative_to(root)),
            "knowledge_matches": compact_knowledge(knowledge),
            "build_log": str((iteration_dir / f"{iteration_id}-build.log").relative_to(root)),
            "compare_log": (
                str((iteration_dir / f"{iteration_id}-compare.log").relative_to(root))
                if compare_code is not None else None
            ),
        }
        append_jsonl(ledger, entry)
        previous_entries.append(entry)

        if build_code != 0:
            if (
                args.allow_build_failure_if_compare_passes
                and compare_code == 0
                and after.get("exact_match")
            ):
                continue
            return 1

        if compare_code != 0:
            return 1

    print(json.dumps({
        "status": "completed",
        "target": args.target,
        "iterations": args.iterations,
        "state": str(state),
        "ledger": str(ledger),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
