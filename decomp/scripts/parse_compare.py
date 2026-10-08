#!/usr/bin/env python3
"""Conservative parser for common matching/decomp comparison output."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PERCENT_PATTERNS = (
    re.compile(r"(?:match(?:ing)?|score|coverage)[^\d]{0,20}(\d+(?:\.\d+)?)\s*%", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:matched|matching|match)", re.I),
)
ADDRESS = r"(?:0x)?[0-9a-fA-F]{4,16}"


def parse_compare(raw: str) -> dict:
    percentages = []
    for pattern in PERCENT_PATTERNS:
        percentages.extend(float(m.group(1)) for m in pattern.finditer(raw))

    lowered = raw.lower()
    exact = bool(
        re.search(
            r"(exact(?:ly)?\s+match|100(?:\.0+)?\s*%\s*(?:match|matched|matching)|"
            r"identical|perfect\s+match|match(?:ing)?\s*[:=]\s*100)",
            lowered,
        )
    )
    failed = bool(re.search(r"build\s+failed|error:|fatal:|failed\b", lowered))

    first_mismatch = None
    patterns = (
        rf"(?:first\s+mismatch|mismatch|expected|actual)[^\n]*?({ADDRESS})",
        rf"(?:at|address)\s+({ADDRESS})",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if match:
            first_mismatch = match.group(1)
            break

    return {
        "exact_match": exact,
        "build_failed": failed,
        "match_percent": max(percentages) if percentages else None,
        "first_mismatch": first_mismatch,
        "evidence_lines": [
            line.strip()
            for line in raw.splitlines()
            if re.search(r"mismatch|match|error|failed|expected|actual", line, re.I)
        ][:40],
    }


def read_input() -> str:
    if len(sys.argv) < 2 or sys.argv[1] == "-":
        return sys.stdin.read()
    return Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    print(json.dumps(parse_compare(read_input()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
