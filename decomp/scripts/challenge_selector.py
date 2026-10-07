#!/usr/bin/env python3
"""Select matching-decompilation candidates that satisfy challenge constraints.

The selector treats an objdiff report as authoritative for remaining progress.
Optional Ghidra scout evidence is used for control-flow and difficulty signals.

Tier 1: zero-percent / undecompiled, non-trivial function.
Tier 2: zero-percent function, >= 256 bytes, >= 75th percentile of the
remaining undecompiled functions, and confirmed control flow.
Tier 3: ranked hard candidates; no automatic claim is made that a function is
"hard" solely from size.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


GENERIC_PREFIXES = ("FUN_", "sub_", "thunk_", "LAB_")
NON_LOGIC_RE = re.compile(
    r"(?:^|[_:])(?:stub|dummy|nop|table|array|vtable|initializer|"
    r"init(?:ializer)?data|dataonly|unimplemented)(?:$|[_:])",
    re.IGNORECASE,
)
ACCESSOR_RE = re.compile(
    r"^(?:get|set|is|has|can)[A-Z_]|::(?:get|set|is|has|can)[A-Z_]",
    re.IGNORECASE,
)


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
    """Return P75 using linear interpolation over sorted values."""
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

        nested = unit.get("functions")
        if isinstance(nested, list):
            functions = nested
        elif any(key in unit for key in ("address", "size", "fuzzy_match_percent")):
            functions = [unit]
        else:
            continue

        for function in functions:
            if not isinstance(function, dict):
                continue

            name = str(function.get("name", unit.get("name", "")))
            size = to_int(function.get("size"))
            address = function.get("address")
            fuzzy_value = function.get("fuzzy_match_percent")
            complete_value = function.get("complete")

            if complete_value is True:
                match_percent = 100.0
            else:
                # objdiff's proto3 JSON may omit default 0 fields.
                match_percent = to_float(fuzzy_value, 0.0)

            rows.append(
                {
                    "name": name,
                    "address": address,
                    "size": size,
                    "match_percent": match_percent,
                    "unit": unit.get("name"),
                    "unit_metadata": unit.get("metadata", {}),
                }
            )

    return rows


def scout_index(scout: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not scout:
        return {}

    index: dict[str, dict[str, Any]] = {}
    for item in scout.get("candidates", []):
        if not isinstance(item, dict):
            continue
        keys = []
        if item.get("name") is not None:
            keys.append(f"name:{item['name']}".lower())
        if item.get("entry") is not None:
            keys.append(f"addr:{str(item['entry']).lower()}")
        for key in keys:
            index[key] = item
    return index


def find_scout(row: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    name = str(row.get("name", ""))
    address = str(row.get("address", ""))
    return (
        index.get(f"addr:{address.lower()}")
        or index.get(f"name:{name}".lower())
        or {}
    )


def obvious_non_logic(name: str) -> tuple[bool, str | None]:
    if NON_LOGIC_RE.search(name):
        return True, "name strongly suggests stub/table/data/initializer code"
    return False, None


def build_candidate(
    row: dict[str, Any],
    scout: dict[str, Any],
    p75: float | None,
    min_tier2_size: int,
) -> dict[str, Any]:
    size = row["size"]
    name = str(row["name"])
    blocks = to_int(scout.get("blocks")) if scout else None
    callees = to_int(scout.get("callees")) if scout else None
    callers = to_int(scout.get("callers")) if scout else None
    globals_count = to_int(scout.get("globals")) if scout else None
    instructions = to_int(scout.get("instructions")) if scout else None

    has_branch = bool(scout.get("has_branch")) if scout else False
    has_loop = bool(scout.get("has_loop")) if scout else False
    has_switch = bool(scout.get("has_switch")) if scout else False
    control_flow_confirmed = has_branch or has_loop or has_switch
    control_flow_inferred = blocks is not None and blocks > 1

    non_logic, non_logic_reason = obvious_non_logic(name)
    is_accessor = bool(ACCESSOR_RE.search(name))

    game_logic_reasons: list[str] = []
    game_logic_penalties: list[str] = []

    if control_flow_confirmed:
        game_logic_reasons.append("confirmed control flow")
    elif control_flow_inferred:
        game_logic_reasons.append("multiple basic blocks; control flow inferred")
    else:
        game_logic_penalties.append("no control-flow evidence")

    if has_loop:
        game_logic_reasons.append("loop/back-edge")
    if has_switch:
        game_logic_reasons.append("switch/indirect control flow")
    if globals_count and globals_count > 0:
        game_logic_reasons.append("references global data")
    if callees and callees > 0:
        game_logic_reasons.append("calls other functions")
    if row["unit"]:
        game_logic_reasons.append(f"unit={row['unit']}")

    if is_accessor:
        game_logic_penalties.append("accessor-like name; requires manual game-logic verification")
    if non_logic_reason:
        game_logic_penalties.append(non_logic_reason)
    if bool(scout.get("is_thunk")) if scout else False:
        game_logic_penalties.append("thunk")
    if bool(scout.get("is_external")) if scout else False:
        game_logic_penalties.append("external")

    if scout:
        signature = str(scout.get("signature", ""))
        if signature and "undefined" not in signature.lower():
            game_logic_reasons.append("resolved signature")
        else:
            game_logic_penalties.append("uncertain signature")

    return {
        **row,
        "instructions": instructions,
        "blocks": blocks,
        "callees": callees,
        "callers": callers,
        "globals": globals_count,
        "has_branch": has_branch,
        "has_loop": has_loop,
        "has_switch": has_switch,
        "control_flow_confirmed": control_flow_confirmed,
        "control_flow_inferred": control_flow_inferred,
        "likely_game_logic": bool(control_flow_confirmed and not non_logic),
        "game_logic_confidence": (
            "high"
            if control_flow_confirmed and not non_logic and not is_accessor
            else "medium"
            if (control_flow_confirmed or control_flow_inferred) and not non_logic
            else "low"
        ),
        "game_logic_reasons": game_logic_reasons,
        "game_logic_penalties": game_logic_penalties,
        "non_logic_name": non_logic,
        "is_accessor_like": is_accessor,
        "tier2_size_threshold": (
            max(min_tier2_size, p75) if p75 is not None else None
        ),
    }


def tier1_score(candidate: dict[str, Any]) -> tuple[float, int, str]:
    size = candidate["size"] if candidate["size"] is not None else 10**9
    blocks = candidate.get("blocks")
    score = 0.0
    score -= min(size, 1000) / 10.0
    if blocks is not None:
        score -= max(0, blocks - 1) * 3.0
    if candidate.get("is_accessor_like"):
        score -= 3.0
    if candidate["name"].startswith(GENERIC_PREFIXES):
        score -= 2.0
    if candidate.get("callees") is not None:
        score -= min(candidate["callees"], 6) * 0.5
    return (score, size, candidate["name"])


def tier2_score(candidate: dict[str, Any], threshold: float) -> tuple[float, int, str]:
    size = candidate["size"] or 0
    ratio = size / max(threshold, 1.0)
    score = 100.0 - min(ratio * 15.0, 60.0)

    blocks = candidate.get("blocks")
    if blocks is not None:
        score -= min(max(blocks - 1, 0), 20) * 1.5
    if candidate.get("has_loop"):
        score += 4.0
    if candidate.get("has_switch"):
        score -= 4.0
    if candidate.get("globals"):
        score -= min(candidate["globals"], 10) * 0.5
    if candidate.get("callees"):
        score -= min(candidate["callees"], 12) * 0.5
    if candidate.get("is_accessor_like"):
        score -= 8.0

    return (-score, -size, candidate["name"])


def tier3_score(candidate: dict[str, Any]) -> tuple[float, int, str]:
    size = candidate["size"] or 0
    score = float(size)
    score += min(candidate.get("blocks") or 0, 40) * 8.0
    score += 20.0 if candidate.get("has_loop") else 0.0
    score += 25.0 if candidate.get("has_switch") else 0.0
    score += min(candidate.get("globals") or 0, 20) * 2.0
    score += min(candidate.get("callees") or 0, 20) * 1.5
    if candidate.get("is_accessor_like"):
        score -= 20.0
    if candidate.get("non_logic_name"):
        score -= 50.0
    return (-score, -size, candidate["name"])


def select(
    report: dict[str, Any],
    scout: dict[str, Any] | None,
    *,
    min_tier1_size: int = 8,
    min_tier2_size: int = 256,
    top: int = 20,
) -> dict[str, Any]:
    rows = function_rows(report)
    remaining = [
        row for row in rows
        if row["match_percent"] < 100.0
        and row["size"] is not None
        and row["size"] > 0
    ]
    undecompiled = [row for row in remaining if row["match_percent"] <= 0.0]
    sizes = [row["size"] for row in undecompiled if row["size"] is not None]
    p75 = percentile75(sizes)
    threshold = max(min_tier2_size, p75) if p75 is not None else None

    index = scout_index(scout)
    candidates = []
    for row in undecompiled:
        evidence = find_scout(row, index)
        candidates.append(build_candidate(row, evidence, p75, min_tier2_size))

    tier1 = [
        item for item in candidates
        if (item["size"] or 0) >= min_tier1_size
        and not item["non_logic_name"]
    ]
    tier1.sort(key=tier1_score)

    tier2 = []
    if threshold is not None:
        tier2 = [
            item for item in candidates
            if (item["size"] or 0) >= threshold
            and not item["non_logic_name"]
            and item["control_flow_confirmed"]
        ]
        tier2.sort(key=lambda item: tier2_score(item, threshold))

    tier3 = [item for item in candidates if not item["non_logic_name"]]
    tier3.sort(key=tier3_score)

    matched = sum(1 for row in rows if row["match_percent"] >= 100.0)
    partial = sum(
        1 for row in rows
        if 0.0 < row["match_percent"] < 100.0
    )
    unknown_size = sum(1 for row in undecompiled if row["size"] is None)

    return {
        "format": "decomp-challenge-selection-v1",
        "report_version": report.get("version"),
        "summary": {
            "total_functions": len(rows),
            "matched_functions": matched,
            "partial_functions": partial,
            "remaining_functions": len(remaining),
            "undecompiled_functions": len(undecompiled),
            "unknown_size_functions": unknown_size,
            "remaining_undecompiled_p75_bytes": p75,
            "tier2_size_threshold_bytes": threshold,
        },
        "tier1": {
            "requirement": f"undecompiled, size >= {min_tier1_size} bytes, not an obvious stub/table/data function",
            "candidates": tier1[:top],
        },
        "tier2": {
            "requirement": (
                f"undecompiled, size >= {min_tier2_size} bytes, "
                "size >= P75(remaining undecompiled), confirmed control flow, "
                "and not an obvious stub/table/data function"
            ),
            "control_flow_note": (
                "Eligibility requires Ghidra scout evidence. Multiple basic "
                "blocks alone are reported as inferred evidence and do not qualify."
            ),
            "candidates": tier2[:top],
        },
        "tier3": {
            "requirement": "ranked by objective complexity signals; manual difficulty argument required",
            "candidates": tier3[:top],
        },
        "policy": {
            "target_report_is_authoritative_for_match_status": True,
            "zero_fuzzy_percent_is_treated_as_undecompiled": True,
            "missing_fuzzy_percent_means_zero": True,
            "tier2_control_flow_requires_scout_confirmation": True,
            "game_logic_is_a_likelihood_and_requires_manual_verification": True,
            "percentile_method": "linear interpolation over sorted remaining undecompiled sizes",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--scout", type=Path)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--tier1-min-size", type=int, default=8)
    parser.add_argument("--tier2-min-size", type=int, default=256)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    if args.top < 1:
        parser.error("--top must be >= 1")
    if args.tier1_min_size < 0 or args.tier2_min_size < 0:
        parser.error("size thresholds must be >= 0")

    scout = load_json(args.scout) if args.scout else None
    result = select(
        load_json(args.report_json),
        scout,
        min_tier1_size=args.tier1_min_size,
        min_tier2_size=args.tier2_min_size,
        top=args.top,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
