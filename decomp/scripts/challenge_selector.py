#!/usr/bin/env python3
"""Backward-compatible CLI wrapper for the unified challenge engine."""

from __future__ import annotations

import argparse
from pathlib import Path

from challenge import evaluate, load_json, percentile75


def select(
    report: dict,
    scout: dict | None = None,
    *,
    min_tier1_size: int = 8,
    min_tier2_size: int = 256,
    top: int = 20,
):
    result = evaluate(report, scout, min_tier2_size=min_tier2_size)
    result["tier1"]["candidates"] = [
        item for item in result["tier1"]["candidates"]
        if (item.get("size") or 0) >= min_tier1_size
    ][:top]
    result["tier2"]["candidates"] = result["tier2"]["candidates"][:top]
    result["tier3"]["candidates"] = result["tier3"]["candidates"][:top]
    return result


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

    result = select(
        load_json(args.report_json),
        load_json(args.scout) if args.scout else None,
        min_tier1_size=args.tier1_min_size,
        min_tier2_size=args.tier2_min_size,
        top=args.top,
    )
    rendered = __import__("json").dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
