#!/usr/bin/env python3
"""Unified challenge selection and candidate-scoring helpers."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from source_inventory import index_sources, lookup
from session_policy import require_allowed


GENERIC_PREFIXES = ("FUN_", "sub_", "LAB_", "thunk_")
NON_LOGIC_RE = re.compile(
    r"(?:^|[_:])(?:stub|dummy|nop|table|array|vtable|initializer|"
    r"init(?:ializer)?data|dataonly|unimplemented)(?:$|[_:])",
    re.IGNORECASE,
)
ACCESSOR_RE = re.compile(
    r"^(?:get|set|is|has|can)[A-Z_]|::(?:get|set|is|has|can)[A-Z_]",
    re.IGNORECASE,
)
CTOR_DTOR_RE = re.compile(r"(?:::|^)(?:~?[A-Z][A-Za-z0-9_]*)$", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 16)
            except ValueError:
                return None
    return None


def to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def percentile75(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * 0.75
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def function_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in report.get("units", []):
        if not isinstance(unit, dict):
            continue
        functions = unit.get("functions")
        if isinstance(functions, list):
            iterable = functions
        elif any(key in unit for key in ("address", "size", "fuzzy_match_percent")):
            iterable = [unit]
        else:
            continue

        for function in iterable:
            if not isinstance(function, dict):
                continue
            fuzzy = function.get("fuzzy_match_percent")
            complete = function.get("complete")
            match = 100.0 if complete is True else to_float(fuzzy, 0.0)
            rows.append({
                "name": str(function.get("name", unit.get("name", ""))),
                "address": function.get("address"),
                "size": to_int(function.get("size")),
                "match_percent": match,
                "unit": unit.get("name"),
                "unit_metadata": unit.get("metadata", {}),
            })
    return rows


def scout_index(scout: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not scout:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in scout.get("candidates", []):
        if not isinstance(item, dict):
            continue
        if item.get("name") is not None:
            index[f"name:{item['name']}".lower()] = item
        if item.get("entry") is not None:
            index[f"addr:{item['entry']}".lower()] = item
    return index


def find_scout(row: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return (
        index.get(f"addr:{str(row.get('address', '')).lower()}")
        or index.get(f"name:{str(row.get('name', '')).lower()}")
        or {}
    )


def obvious_non_logic(name: str) -> tuple[bool, str | None]:
    normalized = re.sub(r"[^A-Za-z0-9_:]+", "_", name).strip("_")
    if NON_LOGIC_RE.search(normalized):
        return True, "name suggests stub/table/data/initializer"
    lowered = normalized.lower()
    if lowered.endswith(("table", "tables", "array", "arrays", "vtable", "initializer", "data")):
        return True, "name suggests table/array/initializer/data"
    return False, None


def match_kind(row: dict[str, Any], source_info: dict[str, Any] | None) -> str:
    if row["match_percent"] >= 100.0:
        return "matched"
    if row["match_percent"] > 0.0:
        return "partial"
    if source_info:
        return "source_nonmatching_or_unverified"
    return "zero_match_no_source"


def logic_evidence(scout: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if scout.get("has_loop"):
        reasons.append("loop")
    if scout.get("has_switch"):
        reasons.append("switch")
    if scout.get("conditional_branches", 0):
        reasons.append("conditional branches")
    elif scout.get("has_branch"):
        reasons.append("branch")
    if scout.get("callees", 0):
        reasons.append("calls")
    if scout.get("globals", 0):
        reasons.append("global/data references")
    if scout.get("stores", 0) or scout.get("has_store"):
        reasons.append("state writes")

    control_flow = bool(
        scout.get("conditional_branches", 0)
        or scout.get("has_branch")
        or scout.get("has_loop")
        or scout.get("has_switch")
    )
    semantic = bool(
        scout.get("has_loop")
        or scout.get("has_switch")
        or scout.get("conditional_branches", 0)
        or scout.get("blocks", 0) >= 3
    )
    return bool(control_flow and semantic), reasons


def scores(
    row: dict[str, Any],
    scout: dict[str, Any],
    source_info: dict[str, Any] | None,
    reference_status: str | None,
) -> dict[str, float]:
    size = row["size"] or 0
    blocks = to_int(scout.get("blocks")) or 0
    callees = to_int(scout.get("callees")) or 0
    callers = to_int(scout.get("callers")) or 0
    globals_count = to_int(scout.get("globals")) or 0
    stores = to_int(scout.get("stores")) or (1 if scout.get("has_store") else 0)
    conditional = to_int(scout.get("conditional_branches")) or 0

    non_logic, _ = obvious_non_logic(str(row["name"]))
    accessor = bool(ACCESSOR_RE.search(str(row["name"])))
    thunk = bool(scout.get("is_thunk")) or str(row["name"]).lower().startswith("thunk")
    generic = str(row["name"]).startswith(GENERIC_PREFIXES)

    success = 50.0
    success += min(15.0, size / 512.0 * 7.5)
    success += min(10.0, blocks / 10.0 * 10.0)
    success += min(8.0, callers * 1.5)
    success += min(10.0, globals_count * 1.5)
    success += min(10.0, stores * 1.5)
    success += 8.0 if source_info else 0.0
    success += 8.0 if reference_status in {"known_nonmatching", "known_nonmatching_equivalent"} else 0.0
    success -= 15.0 if accessor else 0.0
    success -= 25.0 if non_logic else 0.0
    success -= 20.0 if thunk else 0.0
    success -= 5.0 if generic else 0.0
    success -= min(15.0, max(0, callees - 6) * 1.5)
    success -= 8.0 if blocks > 30 else 0.0

    logic = 40.0
    logic += min(20.0, conditional * 2.0)
    logic += 15.0 if scout.get("has_loop") else 0.0
    logic += 15.0 if scout.get("has_switch") else 0.0
    logic += min(15.0, stores * 2.0)
    logic += min(10.0, globals_count)
    logic += min(10.0, callees)
    logic -= 40.0 if accessor else 0.0
    logic -= 50.0 if non_logic else 0.0
    logic = max(0.0, min(100.0, logic))

    return {
        "success_score": round(max(0.0, min(100.0, success)), 2),
        "game_logic_score": round(logic, 2),
        "complexity_score": round(
            min(100.0, size / 2048.0 * 50.0 + blocks * 1.5 + conditional * 1.5 + stores + globals_count),
            2,
        ),
    }


def evaluate(
    report: dict[str, Any],
    scout: dict[str, Any] | None = None,
    *,
    project: Path | None = None,
    reference: dict[str, Any] | None = None,
    min_tier2_size: int = 256,
) -> dict[str, Any]:
    rows = function_rows(report)
    index = scout_index(scout)
    source_map = index_sources(project) if project else {}

    remaining = [
        row for row in rows
        if row["match_percent"] < 100.0 and row["size"] and row["size"] > 0
    ]
    undecompiled = [row for row in remaining if row["match_percent"] <= 0.0]
    p75 = percentile75([row["size"] for row in undecompiled if row["size"]])
    threshold = max(min_tier2_size, p75) if p75 is not None else None

    ref_by_key: dict[str, dict[str, Any]] = {}
    if reference:
        for fn in reference.get("functions", []):
            if not isinstance(fn, dict):
                continue
            for key in (fn.get("name"), fn.get("address")):
                if key is not None:
                    ref_by_key[f"{key}".lower()] = fn

    candidates = []
    rejected = []
    for row in undecompiled:
        evidence = find_scout(row, index)
        source_info = lookup(source_map, str(row["name"])) if source_map else None
        ref = (
            ref_by_key.get(str(row["name"]).lower())
            or ref_by_key.get(str(row["address"]).lower())
        )
        non_logic, non_logic_reason = obvious_non_logic(str(row["name"]))
        logic_ok, logic_reasons = logic_evidence(evidence)

        gates = {
            "zero_match": row["match_percent"] <= 0.0,
            "min_256_bytes": (row["size"] or 0) >= min_tier2_size,
            "min_p75_bytes": threshold is not None and (row["size"] or 0) >= threshold,
            "confirmed_control_flow": bool(
                evidence.get("conditional_branches", 0)
                or evidence.get("has_branch")
                or evidence.get("has_loop")
                or evidence.get("has_switch")
            ),
            "not_obvious_non_logic": not non_logic,
            "not_accessor": not bool(ACCESSOR_RE.search(str(row["name"]))),
            "not_thunk": not bool(evidence.get("is_thunk")),
            "source_or_unresolved": True,
        }
        score = scores(row, evidence, source_info, ref.get("status") if ref else None)
        candidate = {
            **row,
            "match_kind": match_kind(row, source_info),
            "source_exists": source_info is not None,
            "source": source_info,
            "reference": ref,
            "scout": evidence,
            "gates": gates,
            "logic_screen": {
                "passes": logic_ok,
                "reasons": logic_reasons,
                "name_reason": non_logic_reason,
            },
            **score,
        }
        if all(gates.values()) and logic_ok:
            candidates.append(candidate)
        else:
            rejected.append(candidate)

    all_evaluated = candidates + rejected
    candidates.sort(
        key=lambda x: (-x["success_score"], -x["game_logic_score"], -(x["size"] or 0), x["name"])
    )
    rejected.sort(
        key=lambda x: (-x["game_logic_score"], -(x["size"] or 0), x["name"])
    )

    tier1 = [
        item for item in all_evaluated
        if (item.get("size") or 0) >= 8
        and not item["logic_screen"]["name_reason"]
        and item["gates"]["not_accessor"]
        and item["gates"]["not_thunk"]
    ]
    tier1.sort(key=lambda x: ((x.get("size") or 0), -x["success_score"], x["name"]))

    tier3 = [
        item for item in all_evaluated
        if not item["logic_screen"]["name_reason"]
    ]
    tier3.sort(
        key=lambda x: (-x["complexity_score"], -x["game_logic_score"], x["name"])
    )

    return {
        "format": "decomp-challenge-v2",
        "summary": {
            "total_functions": len(rows),
            "matched_functions": sum(1 for row in rows if row["match_percent"] >= 100.0),
            "partial_functions": sum(1 for row in rows if 0.0 < row["match_percent"] < 100.0),
            "remaining_functions": len(remaining),
            "undecompiled_functions": len(undecompiled),
            "p75_bytes": p75,
            "tier2_threshold_bytes": threshold,
            "eligible_candidates": len(candidates),
            "rejected_candidates": len(rejected),
            "p75_method": "linear_interpolation",
            "p75_population": "remaining zero-match functions with known positive machine-code size",
            "remaining_undecompiled_p75_bytes": p75,
            "tier2_size_threshold_bytes": threshold,
        },
        "tier1": {
            "candidates": tier1,
        },
        "tier2": {
            "candidates": candidates,
            "near_miss": rejected[:25],
        },
        "tier3": {
            "candidates": tier3,
        },
    }


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



def compact_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result["summary"]
    candidates = result.get("tier2", {}).get("candidates", [])
    return {
        "format": result["format"],
        "status": "written",
        "remaining_functions": summary["remaining_functions"],
        "undecompiled_functions": summary["undecompiled_functions"],
        "p75_bytes": summary["p75_bytes"],
        "tier2_threshold_bytes": summary["tier2_threshold_bytes"],
        "eligible_candidates": summary["eligible_candidates"],
        "top_tier2": [
            {
                "name": item.get("name"),
                "size": item.get("size"),
                "success_score": item.get("success_score"),
                "game_logic_score": item.get("game_logic_score"),
            }
            for item in candidates[:5]
        ],
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--scout", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-size", type=int, default=256)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--require-policy",
        action="store_true",
        help="Fail when the session policy file is missing.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
        help="Session policy JSON; missing policy means no additional restriction.",
    )

    parser.add_argument(
        "--full-output",
        action="store_true",
        help="Print the full JSON even when --output is used.",
    )
    args = parser.parse_args()

    try:
        require_allowed(args.policy, "select", require_file=args.require_policy)
    except (OSError, ValueError, PermissionError) as exc:
        parser.error(str(exc))

    if args.top < 1 or args.min_size < 0:
        parser.error("invalid top/min-size")

    report = load_json(args.report_json)
    scout = load_json(args.scout) if args.scout else None
    reference = load_json(args.reference) if args.reference else None
    result = evaluate(
        report,
        scout,
        project=args.project,
        reference=reference,
        min_tier2_size=args.min_size,
    )
    result["tier2"]["candidates"] = result["tier2"]["candidates"][:args.top]

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        if args.full_output:
            print(rendered)
        else:
            print(json.dumps(compact_summary(result), indent=2, sort_keys=True))
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
