#!/usr/bin/env python3
"""Gate incomplete objdiff work against a reference decompilation index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalize_source(path: str) -> str:
    value = path.replace("\\", "/")
    for marker in ("/src/", "/libs/", "src/", "libs/"):
        index = value.lower().find(marker.lower())
        if index >= 0:
            return value[index + 1:] if value.startswith("/") else value[index:]
    return value.lstrip("./")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def unit_incomplete(unit: dict[str, Any]) -> bool:
    return not bool(unit.get("metadata", {}).get("complete"))


def functions_for_unit(functions: list[dict[str, Any]], target_path: str) -> list[dict[str, Any]]:
    normalized = normalize_source(target_path)
    return [
        fn for fn in functions
        if normalize_source(str(fn.get("source_file", ""))) == normalized
    ]


def gate(objdiff: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    functions = reference.get("functions", [])
    candidates: list[dict[str, Any]] = []
    blocked_units = 0

    for unit in objdiff.get("units", []):
        target_path = str(unit.get("target_path", unit.get("name", "")))
        if not unit_incomplete(unit):
            continue

        refs = functions_for_unit(functions, target_path)
        status_counts: dict[str, int] = {}
        for fn in refs:
            status = str(fn.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1

        nonmatching = [
            fn for fn in refs
            if fn.get("status") in {"known_nonmatching", "known_nonmatching_equivalent"}
        ]
        unmarked = [fn for fn in refs if fn.get("status") == "unmarked"]

        if refs and not nonmatching and unmarked:
            action = "skip_unit_by_default"
            confidence = "medium"
            reason = "All reference functions found in this unit are unmarked."
            blocked_units += 1
        elif nonmatching:
            action = "inspect_reference_nonmatching"
            confidence = "high"
            reason = "Reference contains explicitly non-matching functions."
        elif refs:
            action = "inspect_reference"
            confidence = "low"
            reason = "Reference evidence exists but is not enough to classify the unit."
        else:
            action = "target_analysis_allowed"
            confidence = "low"
            reason = "No reference function was correlated to this unit."

        candidates.append({
            "name": unit.get("name"),
            "target_path": target_path,
            "metadata_complete": unit.get("metadata", {}).get("complete"),
            "reference_function_count": len(refs),
            "reference_status_counts": status_counts,
            "reference_functions": [
                {
                    "name": fn.get("name"),
                    "address": fn.get("address"),
                    "status": fn.get("status"),
                    "recommended_action": fn.get("recommended_action"),
                }
                for fn in refs
            ],
            "action": action,
            "confidence": confidence,
            "reason": reason,
        })

    return {
        "format": "decomp-candidate-gate-v1",
        "incomplete_units": len(candidates),
        "reference_blocked_units": blocked_units,
        "candidates": candidates,
        "policy": {
            "do_not_redecompile_reference_unmarked_by_default": True,
            "nonmatching_reference_is_reusable_prior_work": True,
            "objdiff_unit_incomplete_is_not_function_match_proof": True,
            "target_authoritative_compare_overrides_reference": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("objdiff_json", type=Path)
    parser.add_argument("reference_json", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    result = gate(load(args.objdiff_json), load(args.reference_json))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    raise SystemExit(main())
