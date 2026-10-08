#!/usr/bin/env python3
"""Build an auditable Tier 2 candidate pack for decompilation challenges."""
#@category Decomp

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from challenge_selector import (
    find_scout,
    function_rows,
    obvious_non_logic,
    percentile75,
    scout_index,
    to_int,
)

ACCESSOR_RE = re.compile(
    r"^(?:get|set|is|has|can)[A-Z_]|::(?:get|set|is|has|can)[A-Z_]",
    re.IGNORECASE,
)
THUNK_RE = re.compile(r"(?:^|[_:])thunk(?:_|$)", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def build_unit_source_index(objdiff: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for unit in objdiff.get("units", []):
        if not isinstance(unit, dict):
            continue
        name = normalize_path(str(unit.get("name", "")))
        source = unit.get("source_path", unit.get("source_file"))
        if isinstance(source, str) and source:
            index[name] = normalize_path(source)
    return index


def logic_screen(row: dict[str, Any], scout: dict[str, Any]) -> tuple[bool, list[str]]:
    name = str(row["name"])
    blocks = to_int(scout.get("blocks")) or 0
    callees = to_int(scout.get("callees")) or 0
    globals_count = to_int(scout.get("globals")) or 0

    has_branch = bool(scout.get("has_branch"))
    has_loop = bool(scout.get("has_loop"))
    has_switch = bool(scout.get("has_switch"))

    non_logic, _ = obvious_non_logic(name)
    if non_logic:
        return False, ["stub/table/initializer/data-like name"]
    if ACCESSOR_RE.search(name):
        return False, ["accessor-like name"]
    if THUNK_RE.search(name) or scout.get("is_thunk"):
        return False, ["thunk"]
    if scout.get("is_external"):
        return False, ["external"]

    reasons = []
    if has_loop:
        reasons.append("loop")
    if has_switch:
        reasons.append("switch")
    if has_branch:
        reasons.append("branch")

    if not (has_branch or has_loop or has_switch):
        return False, ["no confirmed control flow"]

    if has_loop or has_switch:
        return True, reasons

    if has_branch and (callees > 0 or globals_count > 0):
        return True, reasons + ["branch + call/global evidence"]

    if blocks >= 3 and (callees > 0 or globals_count > 0):
        return True, reasons + ["multi-block + call/global evidence"]

    return False, reasons + ["insufficient logic evidence"]


def select_tier2(
    report: dict[str, Any],
    scout: dict[str, Any],
    *,
    min_size: int = 256,
    top: int = 10,
) -> dict[str, Any]:
    rows = function_rows(report)
    remaining = [
        row
        for row in rows
        if row["match_percent"] < 100.0
        and row["size"] is not None
        and row["size"] > 0
    ]
    undecompiled = [row for row in remaining if row["match_percent"] <= 0.0]
    p75 = percentile75([row["size"] for row in undecompiled if row["size"] is not None])
    threshold = max(min_size, p75) if p75 is not None else None

    result: dict[str, Any] = {
        "format": "ph-tier2-autopilot-v1",
        "summary": {
            "total_functions": len(rows),
            "remaining_functions": len(remaining),
            "undecompiled_functions": len(undecompiled),
            "p75_bytes": p75,
            "threshold_bytes": threshold,
            "eligible_candidates": 0,
        },
        "requirements": {
            "zero_match": True,
            "minimum_bytes": min_size,
            "minimum_p75_bytes": True,
            "confirmed_control_flow": True,
            "not_accessor_stub_table_initializer": True,
            "real_game_logic": "heuristic screening plus mandatory manual verification",
        },
        "eligible": [],
    }
    if threshold is None:
        return result

    index = scout_index(scout)
    candidates = []

    for row in undecompiled:
        evidence = find_scout(row, index)
        if not evidence:
            continue

        logic_ok, logic_reasons = logic_screen(row, evidence)
        gates = {
            "zero_match": row["match_percent"] <= 0.0,
            "min_256_bytes": (row["size"] or 0) >= min_size,
            "min_p75_bytes": (row["size"] or 0) >= threshold,
            "confirmed_control_flow": bool(
                evidence.get("has_branch")
                or evidence.get("has_loop")
                or evidence.get("has_switch")
            ),
            "not_accessor_stub_table_initializer": logic_ok,
        }

        if all(gates.values()):
            candidates.append({
                **row,
                "p75_bytes": p75,
                "threshold_bytes": threshold,
                "scout": evidence,
                "gate": gates,
                "logic_evidence": logic_reasons,
                "manual_game_logic_verification_required": True,
            })

    candidates.sort(
        key=lambda item: (
            -(item["size"] or 0),
            -(to_int(item["scout"].get("blocks")) or 0),
            item["name"],
        )
    )

    result["summary"]["eligible_candidates"] = len(candidates)
    result["eligible"] = candidates[:top]
    return result


def run_objdiff(objdiff_cli: Path, project: Path, symbol: str) -> tuple[int, str]:
    result = subprocess.run(
        [str(objdiff_cli), "diff", "-p", str(project), symbol],
        cwd=project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def make_prompt(candidate: dict[str, Any]) -> str:
    scout = candidate["scout"]
    return f"""# Tier 2 target: {candidate["name"]}

Address: {candidate.get("address")}
Size: {candidate["size"]} bytes
Remaining undecompiled P75: {candidate["p75_bytes"]} bytes
Tier 2 threshold: {candidate["threshold_bytes"]} bytes
Current objdiff match: {candidate["match_percent"]}%

Ghidra evidence:
- instructions: {scout.get("instructions")}
- blocks: {scout.get("blocks")}
- branch: {scout.get("has_branch")}
- loop: {scout.get("has_loop")}
- switch: {scout.get("has_switch")}
- callers: {scout.get("callers")}
- callees: {scout.get("callees")}
- globals: {scout.get("globals")}
- signature: {scout.get("signature", "")}

Logic-screen evidence: {", ".join(candidate["logic_evidence"])}

Task:
1. Inspect the current source, Ghidra evidence and objdiff diff.
2. Confirm this is real game logic, not a getter, stub, table initializer or wrapper.
3. Make the smallest source changes needed for this exact function.
4. Build and compare with the authoritative project workflow.
5. Iterate one hypothesis at a time until this function reaches an exact 100% match.
6. Do not switch targets unless this candidate is demonstrably blocked.

Fuzzy similarity or semantic equivalence is not success; only exact machine-code matching counts.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--scout", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--objdiff-json", type=Path)
    parser.add_argument("--objdiff-cli", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-size", type=int, default=256)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--write-packs", action="store_true")
    args = parser.parse_args()

    if args.top < 1 or args.min_size < 0:
        parser.error("invalid top/min-size")

    result = select_tier2(
        load_json(args.report_json),
        load_json(args.scout),
        min_size=args.min_size,
        top=args.top,
    )

    if args.objdiff_json and args.objdiff_json.is_file():
        source_index = build_unit_source_index(load_json(args.objdiff_json))
        for candidate in result["eligible"]:
            candidate["source_path"] = source_index.get(
                normalize_path(str(candidate.get("unit") or ""))
            )

    output = args.output or (
        args.project / ".decomp-agent" / "challenge" / "tier2-selection.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    packs = []
    if args.write_packs:
        if not args.objdiff_cli:
            parser.error("--write-packs requires --objdiff-cli")
        pack_root = output.parent / "candidates"
        pack_root.mkdir(parents=True, exist_ok=True)

        for candidate in result["eligible"]:
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(candidate["name"]))
            pack = pack_root / safe_name
            pack.mkdir(parents=True, exist_ok=True)

            code, diff = run_objdiff(
                args.objdiff_cli,
                args.project.resolve(),
                str(candidate["name"]),
            )
            (pack / "objdiff.txt").write_text(diff, encoding="utf-8")
            (pack / "candidate.json").write_text(
                json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (pack / "codex-prompt.md").write_text(
                make_prompt(candidate),
                encoding="utf-8",
            )
            packs.append({
                "name": candidate["name"],
                "path": str(pack),
                "objdiff_exit": code,
            })

    result["packs"] = packs
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
