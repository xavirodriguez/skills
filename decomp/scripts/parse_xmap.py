#!/usr/bin/env python3
"""Parse linker XMAP files into conservative, machine-readable evidence.

The parser intentionally does not assume one vendor format. It extracts
high-confidence address/name/section/size patterns and preserves raw lines
for entries it cannot classify.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX = r"(?:0x)?[0-9A-Fa-f]+"
ADDRESS_RE = re.compile(rf"(?<![A-Za-z0-9_])(?:0x)?[0-9A-Fa-f]{{6,8}}(?![A-Za-z0-9_])")
SIZE_RE = re.compile(rf"(?<![A-Za-z0-9_])(?:0x)?[0-9A-Fa-f]{{1,8}}(?![A-Za-z0-9_])")
SECTION_RE = re.compile(r"(?<!\w)(\.[A-Za-z0-9_.]+|(?:ITCM|DTCM|TEXT|RODATA|DATA|BSS))(?!\w)", re.I)
SYMBOL_RE = re.compile(
    rf"^\s*(?:(?P<section>\.[A-Za-z0-9_.]+)\s+)?"
    rf"(?P<address>{HEX})\s+"
    rf"(?P<rest>.+?)\s*$"
)

KNOWN_SECTION_NAMES = {
    ".text", ".rodata", ".data", ".bss", ".init", ".itcm", ".dtcm",
    "text", "rodata", "data", "bss", "itcm", "dtcm",
}


def parse_int(value: str) -> int:
    return int(value, 16) if value.lower().startswith("0x") else int(value, 16)


def classify_name(name: str, section: str | None) -> str:
    lower = name.lower()
    if section and section.lower() in {".text", "text", ".itcm", "itcm"}:
        return "probable_function"
    if lower.startswith(("func_", "sub_", "fn_")):
        return "probable_function"
    if lower.startswith(("dat_", "g_", "s_", "d_")):
        return "probable_data"
    if section and section.lower() in {".bss", "bss", ".data", "data", ".rodata", "rodata"}:
        return "probable_data"
    return "unknown"


def parse_line(line: str, line_number: int) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", ";")):
        return None

    match = SYMBOL_RE.match(line)
    if not match:
        return None

    address_text = match.group("address")
    try:
        address = parse_int(address_text)
    except ValueError:
        return None

    rest = match.group("rest")
    tokens = rest.split()
    if not tokens:
        return None

    section = match.group("section")
    if section is None:
        section_match = SECTION_RE.search(rest)
        if section_match and section_match.group(1).lower() in KNOWN_SECTION_NAMES:
            section = section_match.group(1)

    # Avoid treating a line of plain numeric fields as a symbol.
    name_candidates = [token for token in tokens if not re.fullmatch(HEX, token)]
    if not name_candidates:
        return None

    name = name_candidates[-1]
    if name in KNOWN_SECTION_NAMES:
        return None

    return {
        "name": name,
        "address": f"0x{address:08X}",
        "address_int": address,
        "section": section,
        "kind": classify_name(name, section),
        "line": line_number,
        "raw": stripped,
        "confidence": "medium",
    }


def extract_sections(lines: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for number, line in enumerate(lines, 1):
        for match in SECTION_RE.finditer(line):
            name = match.group(1)
            if name.lower() not in KNOWN_SECTION_NAMES:
                continue
            addresses = ADDRESS_RE.findall(line)
            if not addresses:
                continue
            address = parse_int(addresses[0])
            key = (name.lower(), address)
            if key in seen:
                continue
            seen.add(key)
            sections.append({
                "name": name,
                "address": f"0x{address:08X}",
                "address_int": address,
                "line": number,
                "raw": line.strip(),
                "confidence": "medium",
            })
    return sections


def enrich_sizes(symbols: list[dict[str, Any]]) -> None:
    ordered = sorted(symbols, key=lambda item: item["address_int"])
    for index, symbol in enumerate(ordered):
        next_address = (
            ordered[index + 1]["address_int"]
            if index + 1 < len(ordered)
            else None
        )
        if next_address is None or next_address <= symbol["address_int"]:
            continue
        symbol["inferred_size"] = next_address - symbol["address_int"]
        symbol["size_source"] = "next_symbol"
        if symbol["confidence"] == "medium":
            symbol["confidence"] = "medium"


def parse(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    symbols = []

    for number, line in enumerate(lines, 1):
        entry = parse_line(line, number)
        if entry is not None:
            symbols.append(entry)

    enrich_sizes(symbols)

    return {
        "file": str(path),
        "format": {
            "detected": "heuristic-xmap",
            "confidence": "low",
            "note": "No vendor-specific parser was assumed; raw lines are preserved.",
        },
        "statistics": {
            "lines": len(lines),
            "symbols": len(symbols),
            "sections": len(extract_sections(lines)),
        },
        "sections": extract_sections(lines),
        "symbols": symbols,
        "unclassified_lines": [
            {"line": i, "raw": line}
            for i, line in enumerate(lines, 1)
            if line.strip() and parse_line(line, i) is None
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an XMAP into JSON evidence.")
    parser.add_argument("xmap", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    result = parse(args.xmap)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
