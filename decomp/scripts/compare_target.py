#!/usr/bin/env python3
"""Non-interactive objdiff report generation and target extraction."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


TOOL_TRANSPORT_EXIT = 5
TIMEOUT_EXIT = 124


def build_report_args(
    objdiff_cli: Path,
    project: Path,
    report_path: Path,
) -> list[str]:
    return [
        str(objdiff_cli),
        "report",
        "generate",
        "-p",
        str(project),
        "-o",
        str(report_path),
        "-f",
        "json",
    ]


def function_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in report.get("units", []):
        if not isinstance(unit, dict):
            continue
        functions = unit.get("functions")
        if isinstance(functions, list):
            iterable = functions
        elif any(
            key in unit
            for key in ("address", "size", "fuzzy_match_percent")
        ):
            iterable = [unit]
        else:
            continue

        for fn in iterable:
            if not isinstance(fn, dict):
                continue
            fuzzy = fn.get("fuzzy_match_percent")
            complete = fn.get("complete") is True
            match_available = complete
            match: float | None
            if complete:
                match = 100.0
            else:
                try:
                    match = float(fuzzy) if fuzzy is not None else None
                except (TypeError, ValueError):
                    match = None
                match_available = match is not None
            function_entry = fn.get("address")
            function_size = fn.get("size")
            translation_unit = unit.get("name")
            rows.append({
                "name": str(fn.get("name", unit.get("name", ""))),
                "function_entry": function_entry,
                "function_size": function_size,
                "translation_unit": translation_unit,
                # Backward-compatible aliases.
                "address": function_entry,
                "size": function_size,
                "match_percent": match,
                "match_available": match_available,
                "complete": complete,
                "unit": translation_unit,
            })
    return rows


def normalize_address(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    return text.lstrip("0") or "0"


def split_target(target: str) -> tuple[str | None, str | None]:
    if "|" not in target:
        return target, None
    name, address = target.split("|", 1)
    return name or None, address or None


def find_target(rows: list[dict[str, Any]], target: str) -> dict[str, Any]:
    name, address = split_target(target)

    if address:
        addr_matches = [
            row
            for row in rows
            if normalize_address(row.get("address"))
            == normalize_address(address)
        ]
        if name:
            exact = [row for row in addr_matches if row["name"] == name]
            if len(exact) == 1:
                return exact[0]
        if len(addr_matches) == 1:
            return addr_matches[0]
        if len(addr_matches) > 1:
            raise ValueError(f"Target address is ambiguous: {target}")

    name_matches = [
        row for row in rows
        if name is not None and row["name"] == name
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise ValueError(f"Target name is ambiguous: {target}")
    raise ValueError(f"Target not found in objdiff report: {target}")


def run_report(
    objdiff_cli: Path,
    project: Path,
    report_path: Path,
    timeout: float,
) -> tuple[int, str, bool, bool]:
    args = build_report_args(objdiff_cli, project, report_path)
    started = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    try:
        process = subprocess.run(
            args,
            cwd=project,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        return TIMEOUT_EXIT, str(output), True, False
    except (OSError, subprocess.SubprocessError) as exc:
        return TOOL_TRANSPORT_EXIT, f"tool-transport-failure: {exc}", False, True

    elapsed = time.perf_counter() - started
    output = (
        f"{process.stdout}\\n"
        f"[exit={process.returncode}, seconds={elapsed:.3f}]\\n"
    )
    return process.returncode, output, False, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--target", required=True)
    parser.add_argument("--objdiff-cli", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    project = args.project.resolve()
    report_path = (
        args.report.resolve()
        if args.report
        else project / ".decomp-agent" / "compare-target-report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    log = ""
    if not args.report:
        if not args.objdiff_cli:
            parser.error("--objdiff-cli is required unless --report is supplied")
        objdiff_cli = args.objdiff_cli.resolve()
        if not objdiff_cli.is_file():
            payload = {
                "status": "tool-transport-failure",
                "reason": f"objdiff-cli not found: {objdiff_cli}",
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return TOOL_TRANSPORT_EXIT

        code, log, timed_out, transport_failure = run_report(
            objdiff_cli,
            project,
            report_path,
            args.timeout,
        )
        if code != 0:
            payload = {
                "status": (
                    "tool-transport-failure"
                    if transport_failure
                    else "timeout"
                    if timed_out
                    else "compare-failed"
                ),
                "exit_code": code,
                "report": str(report_path),
                "log": log,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return code

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        row = find_target(function_rows(report), args.target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "status": "compare-failed",
            "reason": str(exc),
            "report": str(report_path),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 4

    if not row["match_available"]:
        payload = {
            "status": "compare-incomplete",
            "reason": "Target row has no authoritative match percentage and is not marked complete.",
            "target": args.target,
            "name": row["name"],
            "report": str(report_path),
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 4

    payload = {
        "status": "matched" if row["match_percent"] >= 100.0 else "compare-ran",
        "target": args.target,
        "name": row["name"],
        "function_entry": row["function_entry"],
        "function_size": row["function_size"],
        "translation_unit": row["translation_unit"],
        # Backward-compatible aliases.
        "address": row["function_entry"],
        "size": row["function_size"],
        "match_percent": row["match_percent"],
        "match_available": row["match_available"],
        "exact_match": row["match_percent"] >= 100.0,
        "complete": row["complete"],
        "unit": row["unit"],
        "report": str(report_path),
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
