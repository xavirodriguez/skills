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


def classify_mismatch(raw: str) -> list[str]:
    """Classify common machine-code mismatch families for hypothesis reuse."""
    lowered = raw.lower()
    rules = (
        ("stack_layout", ("stack", "frame", "sp+", "sp -", "sp-")),
        ("register_allocation", ("register", " r0", " r1", " r2", " r3", " r4", " r5", " r6", " r7")),
        ("branch_layout", ("branch", "conditional", "jump", "goto", "control flow")),
        ("load_store_width", ("load", "store", "byte", "halfword", "word", "sign extend", "zero extend")),
        ("address_materialization", ("address", "offset", "symbol", "reloc")),
        ("call_abi", ("call", "argument", "parameter", "calling convention", "abi")),
        ("instruction_shape", ("instruction", "expression", "extra instruction", "missing instruction")),
        ("linker_or_symbol", ("linker", "undefined reference", "relocation")),
    )
    tags = [
        tag
        for tag, keywords in rules
        if any(keyword in lowered for keyword in keywords)
    ]
    return tags or ["unknown"]


def parse_structured_compare(raw: str) -> dict | None:
    candidates = [raw.strip()]
    lines = raw.splitlines()
    candidates.extend(
        line.strip()
        for line in lines
        if line.strip().startswith("{") and line.strip().endswith("}")
    )
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        if "match_percent" not in value and "exact_match" not in value:
            continue
        match_percent = value.get("match_percent")
        if isinstance(match_percent, (int, float)) and not isinstance(match_percent, bool):
            match = float(match_percent)
        else:
            match = None
        return {
            "status": value.get("status"),
            "target": value.get("target"),
            "name": value.get("name"),
            "address": value.get("address", value.get("function_entry")),
            "size": value.get("size", value.get("function_size")),
            "unit": value.get("unit", value.get("translation_unit")),
            "match_percent": match,
            "exact_match": value.get("exact_match") is True or (match is not None and match >= 100.0),
            "compare_data_available": match is not None or value.get("exact_match") is True,
            "first_mismatch": value.get("first_mismatch"),
            "mismatch_tags": classify_mismatch(json.dumps(value, sort_keys=True)),
            "evidence_lines": [json.dumps(value, sort_keys=True)],
        }
    return None

def parse_compare(raw: str) -> dict:
    structured = parse_structured_compare(raw)
    if structured is not None:
        return structured

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
        "mismatch_tags": classify_mismatch(raw),
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
