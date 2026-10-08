#!/usr/bin/env python3
"""Backward-compatible wrapper around the unified challenge engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from challenge import evaluate, load_json


def select_tier2(
    report: dict,
    scout: dict,
    *,
    min_size: int = 256,
    top: int = 10,
) -> dict:
    result = evaluate(report, scout, min_tier2_size=min_size)
    result["eligible"] = result["tier2"]["candidates"][:top]
    result["summary"]["p75_bytes"] = result["summary"]["p75_bytes"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--scout", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--objdiff-json", type=Path)
    parser.add_argument("--objdiff-cli", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-size", type=int, default=256)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--write-packs", action="store_true")
    args = parser.parse_args()

    result = evaluate(
        load_json(args.report_json),
        load_json(args.scout),
        project=args.project,
        reference=load_json(args.reference) if args.reference else None,
        min_tier2_size=args.min_size,
    )
    result["tier2"]["candidates"] = result["tier2"]["candidates"][:args.top]

    output = args.output or (
        args.project / ".decomp-agent" / "challenge" / "tier2-selection.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if args.write_packs:
        if not args.objdiff_cli:
            parser.error("--write-packs requires --objdiff-cli")
        prepare_script = Path(__file__).with_name("prepare_candidate.py")
        for candidate in result["tier2"]["candidates"]:
            command = [
                sys.executable,
                str(prepare_script),
                str(output),
                str(candidate["name"]),
                "--project",
                str(args.project),
                "--objdiff-cli",
                str(args.objdiff_cli),
            ]
            if args.scout:
                command.extend(["--scout-json", str(args.scout)])
            if args.reference:
                command.extend(["--reference-json", str(args.reference)])
            subprocess.run(command, check=True)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
