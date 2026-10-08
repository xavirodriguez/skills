#!/usr/bin/env python3
"""Deterministic post-milestone ROI selection for decompilation targets."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from challenge import (
    file_sha256,
    find_scout,
    function_rows,
    load_json,
    obvious_non_logic,
    scout_index,
    scores,
)
from session_policy import require_allowed


def clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def first_int(item: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value, 0)
            except ValueError:
                continue
    return None


def reference_status(reference: dict[str, Any] | None, row: dict[str, Any]) -> dict[str, Any] | None:
    if not reference:
        return None
    for item in reference.get("functions", []):
        if not isinstance(item, dict):
            continue
        if item.get("name") == row.get("name") or str(item.get("address")).lower() == str(row.get("address")).lower():
            return item
    return None


def score_ease(
    row: dict[str, Any],
    scout: dict[str, Any],
    source_info: dict[str, Any] | None,
    reference: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    base_scores = scores(row, scout, source_info, reference.get("status") if reference else None)
    complexity_ease = 100.0 - base_scores["complexity_score"]
    success = base_scores["success_score"]
    reasons: list[str] = []

    evidence_quality = 20.0
    if scout:
        evidence_quality = 70.0
        reasons.append("fresh static scout evidence")
    if source_info:
        evidence_quality += 10.0
        reasons.append("source context exists")
    if reference and reference.get("reference_build_status") == "complete":
        evidence_quality += 10.0
        reasons.append("verified reference build")
    elif reference:
        evidence_quality += 5.0
        reasons.append("reference evidence exists")

    interworking = bool(scout.get("interworking") or scout.get("has_interworking"))
    ease = (
        complexity_ease * 0.55
        + success * 0.35
        + clamp(evidence_quality) * 0.10
    )
    if interworking:
        ease -= 6.0
        reasons.append("interworking adds codegen risk")
    if not scout:
        ease -= 20.0
        reasons.append("missing static scout evidence")
    if not source_info and not reference:
        ease -= 10.0
        reasons.append("weak source/reference context")

    return clamp(ease), reasons


def score_impact(
    row: dict[str, Any],
    scout: dict[str, Any],
    reference: dict[str, Any] | None,
    source_info: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    callers = first_int(scout, "callers", "caller_count") or 0
    callees = first_int(scout, "callees", "callee_count") or 0
    resolved_callers = first_int(
        scout, "resolved_callers", "decompiled_callers", "known_callers"
    ) or 0
    resolved_callees = first_int(
        scout, "resolved_callees", "decompiled_callees", "known_callees"
    ) or 0
    globals_count = first_int(scout, "globals", "global_count") or 0
    size = row.get("size") or 0

    impact = 10.0
    reasons: list[str] = []

    if callers:
        impact += min(35.0, callers * 3.5)
        reasons.append(f"{callers} callers")
    if resolved_callers:
        impact += min(15.0, resolved_callers * 5.0)
        reasons.append(f"{resolved_callers} resolved callers")
    if callees:
        impact += min(15.0, callees * 1.5)
        reasons.append(f"{callees} callees")
    if resolved_callees:
        impact += min(10.0, resolved_callees * 5.0)
        reasons.append(f"{resolved_callees} resolved callees")
    if globals_count:
        impact += min(10.0, globals_count * 2.0)
        reasons.append(f"{globals_count} global/data references")
    if reference:
        impact += 10.0
        reasons.append("reference-decompilation context")
    if source_info:
        impact += 5.0
        reasons.append("source/API context")
    if size >= 512:
        impact += 5.0
        reasons.append("substantial code body")

    return clamp(impact), reasons


def score_unlock(
    row: dict[str, Any],
    scout: dict[str, Any],
    reference: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    callers = first_int(scout, "callers", "caller_count") or 0
    callees = first_int(scout, "callees", "callee_count") or 0
    resolved_callers = first_int(
        scout, "resolved_callers", "decompiled_callers", "known_callers"
    ) or 0
    resolved_callees = first_int(
        scout, "resolved_callees", "decompiled_callees", "known_callees"
    ) or 0
    globals_count = first_int(scout, "globals", "global_count") or 0
    struct_count = first_int(
        scout, "known_structs", "structs", "known_types", "types", "global_types"
    ) or 0

    unlock = 5.0
    reasons: list[str] = []

    connectivity = callers + callees
    if connectivity:
        unlock += min(25.0, connectivity * 2.0)
        reasons.append("high call-graph connectivity")
    if resolved_callers or resolved_callees:
        unlock += min(15.0, (resolved_callers * 2.5) + (resolved_callees * 5.0))
        reasons.append("connects known code to unresolved code")
    if globals_count:
        unlock += min(20.0, globals_count * 4.0)
        reasons.append("can clarify shared state/global layout")
    if struct_count:
        unlock += min(20.0, struct_count * 5.0)
        reasons.append("may confirm reusable type/structure information")
    if scout.get("has_loop") or scout.get("has_switch"):
        unlock += 8.0
        reasons.append("distinct control-flow pattern can become an anchor")
    if reference:
        unlock += 7.0
        reasons.append("reference evidence can transfer to similar functions")

    return clamp(unlock), reasons


def unit_completion(report: dict[str, Any]) -> dict[str, bool]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in function_rows(report):
        groups[str(row.get("unit", ""))].append(row)
    result: dict[str, bool] = {}
    for unit, rows in groups.items():
        known = [row for row in rows if row.get("match_available")]
        result[unit] = bool(known) and len(known) == len(rows) and all(
            row["match_percent"] >= 100.0 for row in known
        )
    return result


def exact_keys(report: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(row.get("name")), str(row.get("address")))
        for row in function_rows(report)
        if row.get("match_available") and row["match_percent"] >= 100.0
    }


def milestone_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if previous is None:
        return {
            "available": False,
            "newly_completed_units": [],
            "new_exact_functions": 0,
        }

    before_units = unit_completion(previous)
    after_units = unit_completion(current)
    newly_completed = sorted(
        unit for unit, complete in after_units.items()
        if complete and not before_units.get(unit, False)
    )
    new_exact = len(exact_keys(current) - exact_keys(previous))
    return {
        "available": True,
        "newly_completed_units": newly_completed,
        "new_exact_functions": new_exact,
    }


def select(
    report: dict[str, Any],
    scout: dict[str, Any] | None = None,
    *,
    project: Path | None = None,
    reference: dict[str, Any] | None = None,
    previous_report: dict[str, Any] | None = None,
    top: int = 5,
) -> dict[str, Any]:
    rows = function_rows(report)
    index = scout_index(scout)
    source_map = {}
    if project:
        from source_inventory import index_sources
        source_map = index_sources(project)

    ranked: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("match_available"):
            continue
        if row["match_percent"] > 0.0 or not row.get("size") or row["size"] <= 4:
            continue

        non_logic, non_logic_reason = obvious_non_logic(str(row["name"]))
        if non_logic:
            continue

        scout_item = find_scout(row, index)
        source_info = None
        if source_map:
            from source_inventory import lookup
            source_info = lookup(source_map, str(row["name"]))
        ref = reference_status(reference, row)
        ease, ease_reasons = score_ease(row, scout_item, source_info, ref)
        impact, impact_reasons = score_impact(row, scout_item, ref, source_info)
        unlock, unlock_reasons = score_unlock(row, scout_item, ref)
        roi = clamp(ease * impact / 100.0)

        penalty = 0.0
        if non_logic:
            penalty = 20.0
        if penalty:
            roi = clamp(roi - penalty)

        priority = "WATCH"
        if roi >= 70.0 and unlock >= 70.0:
            priority = "ATTACK"
        elif roi >= 60.0 or unlock >= 80.0:
            priority = "NEXT"

        ranked.append({
            **row,
            "scout": scout_item,
            "source_exists": source_info is not None,
            "reference": ref,
            "ease_score": ease,
            "impact_score": impact,
            "unlock_score": unlock,
            "roi_score": roi,
            "priority": priority,
            "anchor_potential": unlock,
            "evidence": {
                "ease": ease_reasons,
                "impact": impact_reasons,
                "unlock": unlock_reasons,
                "non_logic_reason": non_logic_reason,
            },
        })

    ranked.sort(
        key=lambda item: (
            -item["roi_score"],
            -item["unlock_score"],
            -item["ease_score"],
            -item["impact_score"],
            -(item.get("size") or 0),
            item["name"],
        )
    )
    selected = ranked[:top]

    return {
        "format": "decomp-roi-selection-v1",
        "selection_policy": {
            "zero_match_only": True,
            "unknown_match_excluded": True,
            "exact_matches_excluded": True,
            "roi_formula": "ease_score * impact_score / 100",
            "unlock_is_tiebreaker": True,
            "read_only": True,
        },
        "milestone": milestone_delta(previous_report, report),
        "summary": {
            "total_functions": len(rows),
            "candidate_universe": len(ranked),
            "returned": len(selected),
            "requested": top,
        },
        "candidates": selected,
    }


def provenance(
    result: dict[str, Any],
    *,
    report: Path,
    scout: Path | None,
    reference: Path | None,
    previous_report: Path | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "decomp-selection-provenance-v1",
        "engine": result["format"],
        "report": {
            "path": str(report.resolve()),
            "sha256": file_sha256(report.resolve()),
        },
    }
    for key, path in (
        ("scout", scout),
        ("reference", reference),
        ("previous_report", previous_report),
    ):
        if path is not None:
            data[key] = {
                "path": str(path.resolve()),
                "sha256": file_sha256(path.resolve()),
            }
    return data


def compact_summary(result: dict[str, Any]) -> dict[str, Any]:
    candidates = result["candidates"]
    return {
        "format": result["format"],
        "status": "written",
        "candidate_universe": result["summary"]["candidate_universe"],
        "returned": result["summary"]["returned"],
        "milestone": result["milestone"],
        "top5": [
            {
                "rank": index,
                "name": item["name"],
                "address": item["address"],
                "size": item["size"],
                "ease_score": item["ease_score"],
                "impact_score": item["impact_score"],
                "unlock_score": item["unlock_score"],
                "roi_score": item["roi_score"],
                "priority": item["priority"],
            }
            for index, item in enumerate(candidates, start=1)
        ],
        "recommended_next": candidates[0]["name"] if candidates else None,
        "expected_unlock": candidates[0]["evidence"]["unlock"] if candidates else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--scout", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--previous-report", type=Path)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--full-output", action="store_true")
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )
    parser.add_argument("--require-policy", action="store_true")
    args = parser.parse_args()

    if args.top < 1:
        parser.error("top must be >= 1")

    try:
        require_allowed(args.policy, "select", require_file=args.require_policy)
    except (OSError, ValueError, PermissionError) as exc:
        parser.error(str(exc))

    report = load_json(args.report_json)
    scout = load_json(args.scout) if args.scout else None
    reference = load_json(args.reference) if args.reference else None
    previous = load_json(args.previous_report) if args.previous_report else None
    result = select(
        report,
        scout,
        project=args.project,
        reference=reference,
        previous_report=previous,
        top=args.top,
    )
    result["provenance"] = provenance(
        result,
        report=args.report_json,
        scout=args.scout,
        reference=args.reference,
        previous_report=args.previous_report,
    )

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
