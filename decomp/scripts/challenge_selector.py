#!/usr/bin/env python3
"""Backward-compatible wrapper for the unified challenge module.

New code should use challenge.py directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from challenge import evaluate, load_json


def select(
    report: dict,
    scout: dict | None = None,
    *,
    min_tier1_size: int = 8,
    min_tier2_size: int = 256,
    top: int = 20,
):
    result = evaluate(report, scout, min_tier2_size=min_tier2_size)
    rows = result["tier2"]["candidates"]
    tier1 = []
    # Preserve the old public shape for existing users/tests.
    for item in result["tier2"]["near_miss"]:
        if (item.get("size") or 0) >= min_tier1_size and not item["logic_screen"]["name_reason"]:
            tier1.append(item)
    tier1.extend(
        item for item in rows if (item.get("size") or 0) >= min_tier1_size
    )
    tier1.sort(key=lambda item: (item.get("size") or 0, item["name"]))

    matched = sum(1 for row in result["tier2"]["candidates"] if row["match_percent"] >= 100.0)
    partial = sum(1 for row in result["tier2"]["near_miss"] if 0.0 < row["match_percent"] < 100.0)

    return {
        "format": "decomp-challenge-selection-v1-compat",
        "summary": {
            "total_functions": result["summary"]["total_functions"],
            "matched_functions": matched,
            "partial_functions": partial,
            "remaining_functions": result["summary"]["remaining_functions"],
            "undecompiled_functions": result["summary"]["undecompiled_functions"],
            "unknown_size_functions": 0,
            "remaining_undecompiled_p75_bytes": result["summary"]["p75_bytes"],
            "tier2_size_threshold_bytes": result["summary"]["tier2_threshold_bytes"],
        },
        "tier1": {"candidates": tier1[:top]},
        "tier2": {
            "candidates": rows[:top],
            "requirement": "compatibility view; use challenge.py for authoritative challenge selection",
        },
        "tier3": {"candidates": []},
        "policy": {
            "deprecated": True,
            "use_unified_challenge_module": True,
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
