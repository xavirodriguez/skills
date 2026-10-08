#!/usr/bin/env python3
"""Persistent autonomous challenge queue and batch orchestration."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from challenge import evaluate, load_json
from session_policy import require_allowed


SESSION_FORMAT = "decomp-challenge-session-v1"
DEFAULT_MAX_STAGNATION = 3


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_session(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Session file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(path: Path, session: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(session, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def candidate_key(name: str, address: Any) -> str:
    return f"{name}|{address}"


def expected_value(candidate: dict[str, Any], history: dict[str, Any] | None = None) -> float:
    success = float(candidate.get("success_score") or 0)
    logic = float(candidate.get("game_logic_score") or 0)
    complexity = min(100.0, max(0.0, float(candidate.get("complexity_score") or 0)))
    ease = 100.0 - complexity
    size = float(candidate.get("size") or 0)
    threshold = float(candidate.get("threshold_bytes") or candidate.get("p75_bytes") or 256)
    size_value = min(100.0, size / max(1.0, threshold) * 100.0)

    value = success * 0.55 + logic * 0.20 + ease * 0.15 + size_value * 0.10

    if history:
        attempts = int(history.get("attempts") or 0)
        stagnation = int(history.get("stagnation") or 0)
        value -= min(20.0, attempts * 2.0)
        value -= min(20.0, stagnation * 8.0)

    return round(max(0.0, min(100.0, value)), 2)


def tier_candidates(evaluation: dict[str, Any], tier: str) -> list[dict[str, Any]]:
    if tier == "tier1":
        return list(evaluation.get("tier1", {}).get("candidates", []))
    if tier == "tier2":
        return list(evaluation.get("tier2", {}).get("candidates", []))
    if tier == "tier3":
        return list(evaluation.get("tier3", {}).get("candidates", []))
    raise ValueError(f"Unsupported tier: {tier}")


def merge_candidates(
    session: dict[str, Any],
    evaluation: dict[str, Any],
) -> None:
    tier = str(session["tier"])
    candidates = tier_candidates(evaluation, tier)
    by_key = {
        candidate_key(str(item["name"]), item.get("address")): item
        for item in candidates
    }

    queue = session.setdefault("queue", [])
    existing = {
        str(item.get("key")): item
        for item in queue
        if isinstance(item, dict) and item.get("key")
    }

    for key, candidate in by_key.items():
        item = existing.get(key)
        if item is None:
            item = {
                "key": key,
                "name": candidate.get("name"),
                "address": candidate.get("address"),
                "status": "pending",
                "attempts": 0,
                "stagnation": 0,
                "match_before": candidate.get("match_percent"),
                "match_after": candidate.get("match_percent"),
                "last_mismatch": None,
                "last_lesson": None,
                "created_at": now_utc(),
            }
            queue.append(item)

        item.update({
            "size": candidate.get("size"),
            "success_score": candidate.get("success_score"),
            "game_logic_score": candidate.get("game_logic_score"),
            "complexity_score": candidate.get("complexity_score"),
            "expected_value_score": expected_value(candidate, item),
            "gates": candidate.get("gates", {}),
            "match_kind": candidate.get("match_kind"),
        })

        current_match = float(candidate.get("match_percent") or 0)
        item["last_report_match"] = current_match
        if current_match >= 100.0:
            item["status"] = "matched"
            item["matched_at"] = item.get("matched_at") or now_utc()
        elif item.get("status") == "pending":
            item["status"] = "pending"

    # Preserve an active target even if its match percentage moved it outside
    # the selector's zero-match population.
    active = session.get("current_target")
    if active and active in existing:
        existing[active]["status"] = "active"


def init_session(
    path: Path,
    evaluation: dict[str, Any],
    *,
    tier: str,
    quota: int,
    max_stagnation: int,
    replace: bool,
) -> dict[str, Any]:
    if path.exists() and not replace:
        session = load_session(path)
        merge_candidates(session, evaluation)
        save_session(path, session)
        return session

    session = {
        "format": SESSION_FORMAT,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "tier": tier,
        "target_quota": quota,
        "matches_completed": 0,
        "max_stagnation": max_stagnation,
        "current_target": None,
        "halted": False,
        "stop_reason": None,
        "queue": [],
        "history": [],
    }
    merge_candidates(session, evaluation)
    save_session(path, session)
    return session


def choose_next(session: dict[str, Any]) -> dict[str, Any] | None:
    current_key = session.get("current_target")
    queue = session.get("queue", [])

    if current_key:
        current = next(
            (item for item in queue if item.get("key") == current_key),
            None,
        )
        if current and current.get("status") == "active":
            return current

    pending = [
        item for item in queue
        if item.get("status") == "pending"
    ]
    if not pending:
        return None

    pending.sort(
        key=lambda item: (
            -float(item.get("expected_value_score") or 0),
            -float(item.get("success_score") or 0),
            -float(item.get("game_logic_score") or 0),
            -float(item.get("size") or 0),
            str(item.get("name") or ""),
        )
    )
    return pending[0]


def claim_next(session: dict[str, Any]) -> dict[str, Any] | None:
    candidate = choose_next(session)
    if candidate is None:
        return None

    candidate["status"] = "active"
    session["current_target"] = candidate["key"]
    session["updated_at"] = now_utc()
    return candidate


def record_result(
    session: dict[str, Any],
    *,
    target: str,
    match_before: float,
    match_after: float,
    exact: bool,
    mismatch: str | None,
    lesson: str | None,
    infrastructure_blocker: bool,
) -> dict[str, Any]:
    queue = session.get("queue", [])
    candidate = next(
        (item for item in queue if item.get("name") == target or item.get("key") == target),
        None,
    )
    if candidate is None:
        raise ValueError(f"Target is not present in session queue: {target}")

    candidate["attempts"] = int(candidate.get("attempts") or 0) + 1
    candidate["match_before"] = match_before
    candidate["match_after"] = match_after
    candidate["last_mismatch"] = mismatch
    candidate["last_lesson"] = lesson
    candidate["last_attempt_at"] = now_utc()

    if exact or match_after >= 100.0:
        candidate["status"] = "matched"
        candidate["stagnation"] = 0
        candidate["matched_at"] = now_utc()
        session["matches_completed"] = sum(
            1 for item in queue if item.get("status") == "matched"
        )
        if session.get("current_target") == candidate["key"]:
            session["current_target"] = None
    elif infrastructure_blocker:
        session["halted"] = True
        session["stop_reason"] = "infrastructure-blocker"
    elif match_after > match_before:
        candidate["status"] = "active"
        candidate["stagnation"] = 0
    else:
        candidate["status"] = "active"
        candidate["stagnation"] = int(candidate.get("stagnation") or 0) + 1
        if candidate["stagnation"] >= int(session.get("max_stagnation") or DEFAULT_MAX_STAGNATION):
            candidate["status"] = "blocked"
            candidate["blocked_reason"] = "stagnation"
            candidate["blocked_at"] = now_utc()
            candidate["stagnation_limit"] = session.get("max_stagnation")
            if session.get("current_target") == candidate["key"]:
                session["current_target"] = None

    session.setdefault("history", []).append({
        "timestamp": now_utc(),
        "target": candidate.get("name"),
        "match_before": match_before,
        "match_after": match_after,
        "delta": round(match_after - match_before, 4),
        "exact": exact,
        "mismatch": mismatch,
        "lesson": lesson,
        "status": candidate.get("status"),
        "stagnation": candidate.get("stagnation"),
    })
    session["updated_at"] = now_utc()
    session["matches_completed"] = sum(
        1 for item in queue if item.get("status") == "matched"
    )
    quota = int(session.get("target_quota") or 0)
    if quota > 0 and session["matches_completed"] >= quota:
        session["halted"] = True
        session["stop_reason"] = "quota-reached"
    return candidate


def refresh_report(
    session_path: Path,
    *,
    refresh_command: str,
    report_path: Path,
    scout_path: Path | None,
    reference_path: Path | None,
    project: Path,
    shell: str,
) -> tuple[int, dict[str, Any]]:
    from run_match import build_process_args

    session = load_session(session_path)
    refresh_dir = project / ".decomp-agent" / "challenge"
    refresh_dir.mkdir(parents=True, exist_ok=True)
    refresh_number = len(list(refresh_dir.glob("refresh-*.log"))) + 1
    log_path = refresh_dir / f"refresh-{refresh_number:03d}.log"

    started = time.perf_counter()
    try:
        process = subprocess.run(
            build_process_args(refresh_command, shell),
            cwd=project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        session["halted"] = True
        session["stop_reason"] = f"refresh-command-error: {exc}"
        save_session(session_path, session)
        return 127, session

    elapsed = round(time.perf_counter() - started, 3)
    log_path.write_text(
        f"$ [{shell}] {refresh_command}\n\n{process.stdout}\n\n"
        f"[exit={process.returncode}, seconds={elapsed}]\n",
        encoding="utf-8",
    )
    session["last_refresh"] = {
        "command": refresh_command,
        "report": str(report_path),
        "log": str(log_path.relative_to(project)),
        "exit_code": process.returncode,
        "elapsed_seconds": elapsed,
        "timestamp": now_utc(),
    }

    if process.returncode != 0:
        session["halted"] = True
        session["stop_reason"] = "report-refresh-failed"
        save_session(session_path, session)
        return process.returncode, session

    evaluation = evaluate(
        load_json(report_path),
        load_json(scout_path) if scout_path else None,
        project=project,
        reference=load_json(reference_path) if reference_path else None,
    )
    merge_candidates(session, evaluation)
    save_session(session_path, session)
    return 0, session


def compact(session: dict[str, Any]) -> dict[str, Any]:
    queue = session.get("queue", [])
    pending = [x for x in queue if x.get("status") == "pending"]
    active = [x for x in queue if x.get("status") == "active"]
    matched = [x for x in queue if x.get("status") == "matched"]
    blocked = [x for x in queue if x.get("status") == "blocked"]
    return {
        "format": session.get("format"),
        "tier": session.get("tier"),
        "target_quota": session.get("target_quota"),
        "matches_completed": session.get("matches_completed"),
        "current_target": session.get("current_target"),
        "halted": session.get("halted"),
        "stop_reason": session.get("stop_reason"),
        "counts": {
            "pending": len(pending),
            "active": len(active),
            "matched": len(matched),
            "blocked": len(blocked),
        },
        "next": sorted(
            pending,
            key=lambda x: (
                -float(x.get("expected_value_score") or 0),
                -float(x.get("success_score") or 0),
                str(x.get("name") or ""),
            ),
        )[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=Path("."))
    common.add_argument(
        "--session",
        type=Path,
        default=Path(".decomp-agent/challenge/session.json"),
    )
    common.add_argument("--report", type=Path, required=True)
    common.add_argument("--scout", type=Path)
    common.add_argument("--reference", type=Path)
    common.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )
    common.add_argument("--require-policy", action="store_true")

    init = sub.add_parser("init", parents=[common])
    init.add_argument("--tier", choices=("tier1", "tier2", "tier3"), default="tier2")
    init.add_argument("--quota", type=int, default=0, help="0 means continue until no candidates or a blocker.")
    init.add_argument("--max-stagnation", type=int, default=DEFAULT_MAX_STAGNATION)
    init.add_argument("--replace", action="store_true")

    sync = sub.add_parser("sync", parents=[common])

    nxt = sub.add_parser("next")
    nxt.add_argument("--session", type=Path, default=Path(".decomp-agent/challenge/session.json"))
    nxt.add_argument("--claim", action="store_true")

    record = sub.add_parser("record")
    record.add_argument("--session", type=Path, default=Path(".decomp-agent/challenge/session.json"))
    record.add_argument("--target", required=True)
    record.add_argument("--before", type=float, required=True)
    record.add_argument("--after", type=float, required=True)
    record.add_argument("--exact", action="store_true")
    record.add_argument("--mismatch", default="")
    record.add_argument("--lesson", default="")
    record.add_argument("--infrastructure-blocker", action="store_true")

    refresh = sub.add_parser("refresh")
    refresh.add_argument("--session", type=Path, default=Path(".decomp-agent/challenge/session.json"))
    refresh.add_argument("--project", type=Path, default=Path("."))
    refresh.add_argument("--refresh-command", required=True)
    refresh.add_argument("--report", type=Path, required=True)
    refresh.add_argument("--scout", type=Path)
    refresh.add_argument("--reference", type=Path)
    refresh.add_argument("--shell", choices=("powershell", "pwsh", "bash", "cmd"), default="powershell")
    refresh.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )
    refresh.add_argument("--require-policy", action="store_true")

    skip = sub.add_parser("skip")
    skip.add_argument("--session", type=Path, default=Path(".decomp-agent/challenge/session.json"))
    skip.add_argument("--target", required=True)
    skip.add_argument("--reason", required=True)

    status = sub.add_parser("status")
    status.add_argument("--session", type=Path, default=Path(".decomp-agent/challenge/session.json"))

    args = parser.parse_args()

    if args.command in {"init", "sync"}:
        try:
            require_allowed(
                args.policy,
                "select",
                require_file=args.require_policy,
            )
        except (OSError, ValueError, PermissionError) as exc:
            parser.error(str(exc))

        evaluation = evaluate(
            load_json(args.report),
            load_json(args.scout) if args.scout else None,
            project=args.project,
            reference=load_json(args.reference) if args.reference else None,
        )
        if args.command == "init":
            if args.quota < 0 or args.max_stagnation < 1:
                parser.error("quota must be >= 0 and max-stagnation must be >= 1")
            session = init_session(
                args.session,
                evaluation,
                tier=args.tier,
                quota=args.quota,
                max_stagnation=args.max_stagnation,
                replace=args.replace,
            )
        else:
            session = load_session(args.session)
            merge_candidates(session, evaluation)
            session["updated_at"] = now_utc()
            save_session(args.session, session)
        print(json.dumps(compact(session), indent=2, sort_keys=True))
        return 0

    session = load_session(args.session)

    if args.command == "next":
        candidate = claim_next(session) if args.claim else choose_next(session)
        save_session(args.session, session)
        print(json.dumps(candidate or {"status": "no-candidate"}, indent=2, sort_keys=True))
        return 0 if candidate else 1

    if args.command == "record":
        candidate = record_result(
            session,
            target=args.target,
            match_before=args.before,
            match_after=args.after,
            exact=args.exact,
            mismatch=args.mismatch or None,
            lesson=args.lesson or None,
            infrastructure_blocker=args.infrastructure_blocker,
        )
        save_session(args.session, session)
        print(json.dumps(candidate, indent=2, sort_keys=True))
        return 0

    if args.command == "refresh":
        try:
            require_allowed(
                args.policy,
                "build",
                require_file=args.require_policy,
            )
        except (OSError, ValueError, PermissionError) as exc:
            parser.error(str(exc))

        code, refreshed = refresh_report(
            args.session,
            refresh_command=args.refresh_command,
            report_path=args.report,
            scout_path=args.scout,
            reference_path=args.reference,
            project=args.project,
            shell=args.shell,
        )
        print(json.dumps(compact(refreshed), indent=2, sort_keys=True))
        return code

    if args.command == "skip":
        candidate = next(
            (item for item in session.get("queue", []) if item.get("name") == args.target),
            None,
        )
        if candidate is None:
            raise SystemExit(f"Target not found: {args.target}")
        candidate["status"] = "blocked"
        candidate["blocked_reason"] = args.reason
        candidate["blocked_at"] = now_utc()
        if session.get("current_target") == candidate.get("key"):
            session["current_target"] = None
        session["updated_at"] = now_utc()
        save_session(args.session, session)
        print(json.dumps(candidate, indent=2, sort_keys=True))
        return 0

    if args.command == "status":
        print(json.dumps(compact(session), indent=2, sort_keys=True))
        return 0

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
