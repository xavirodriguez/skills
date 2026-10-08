#!/usr/bin/env python3
"""Correlate target functions with reference-decompilation evidence.

The gate is deliberately function-level. An incomplete translation unit does
not block every function in that unit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from challenge import function_rows


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def key(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def ref_index(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for fn in reference.get("functions", []):
        if not isinstance(fn, dict):
            continue
        for value in (fn.get("name"), fn.get("address")):
            if value is not None:
                result[key(value)] = fn
    return result


def gate(objdiff: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    index = ref_index(reference)
    functions = []
    for row in function_rows(objdiff):
        if row["match_percent"] >= 100.0:
            continue

        ref = index.get(key(row["name"])) or index.get(key(row["address"]))
        status = ref.get("status") if ref else None

        if status == "known_nonmatching_equivalent":
            action = "reuse_reference_codegen"
            confidence = "high"
        elif status == "known_nonmatching":
            action = "reuse_reference_and_match"
            confidence = "high"
        elif status == "unmarked" and ref and ref.get("reference_build_status") == "complete":
            action = "reuse_verified_reference"
            confidence = "high"
        elif status == "unmarked":
            action = "reuse_reference_apparently_matching"
            confidence = "medium"
        else:
            action = "new_target_analysis"
            confidence = "low"

        functions.append({
            **row,
            "reference": {
                "name": ref.get("name") if ref else None,
                "address": ref.get("address") if ref else None,
                "source_file": ref.get("source_file") if ref else None,
                "line": ref.get("line") if ref else None,
                "status": status,
                "reference_build_status": ref.get("reference_build_status") if ref else None,
                "recommended_action": ref.get("recommended_action") if ref else None,
            },
            "action": action,
            "confidence": confidence,
        })

    return {
        "format": "decomp-candidate-gate-v2",
        "functions": functions,
        "summary": {
            "target_incomplete_functions": len(functions),
            "reference_matches": sum(1 for item in functions if item["reference"]["name"]),
            "reuse_reference": sum(
                1 for item in functions
                if item["action"].startswith("reuse_reference")
            ),
            "new_target_analysis": sum(
                1 for item in functions if item["action"] == "new_target_analysis"
            ),
        },
        "policy": {
            "unit_incompleteness_does_not_block_function": True,
            "function_level_reference_correlation": True,
            "reference_is_context_not_authority": True,
            "target_objdiff_is_authoritative": True,
        },
    }


def compact_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result["summary"]
    actions: dict[str, int] = {}
    for item in result["functions"]:
        action = str(item.get("action", "unknown"))
        actions[action] = actions.get(action, 0) + 1

    return {
        "format": result["format"],
        "status": "written",
        "target_incomplete_functions": summary["target_incomplete_functions"],
        "reference_matches": summary["reference_matches"],
        "reuse_reference": summary["reuse_reference"],
        "new_target_analysis": summary["new_target_analysis"],
        "actions": dict(sorted(actions.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("objdiff_json", type=Path)
    parser.add_argument("reference_json", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--full-output",
        action="store_true",
        help="Print the full JSON even when --output is used.",
    )
    args = parser.parse_args()

    result = gate(load(args.objdiff_json), load(args.reference_json))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
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
