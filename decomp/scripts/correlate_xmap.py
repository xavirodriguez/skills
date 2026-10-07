#!/usr/bin/env python3
"""Correlate parsed XMAP symbols with a Ghidra program evidence export.

The correlation is intentionally address-first. It never treats a virtual
address as a ROM/file offset and never auto-infers an address delta.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value, 0) if value.lower().startswith("0x") else int(value, 16)


def parse_offset(value: str) -> int:
    text = value.strip()
    sign = -1 if text.startswith("-") else 1
    if text[:1] in "+-":
        text = text[1:]
    base = 16 if text.lower().startswith("0x") else 10
    return sign * int(text, base)


def address_value(entry: dict[str, Any]) -> int | None:
    if isinstance(entry.get("address_int"), int):
        return entry["address_int"]
    address = entry.get("address")
    if address is None:
        return None
    try:
        return parse_int(str(address))
    except ValueError:
        return None


def index_entries(entries: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    indexed: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        address = address_value(entry)
        if address is None:
            continue
        indexed.setdefault(address, []).append(entry)
    return indexed


def correlate(
    xmap: dict[str, Any],
    ghidra: dict[str, Any],
    address_offset: int = 0,
) -> dict[str, Any]:
    xmap_symbols = xmap.get("symbols", [])
    functions = ghidra.get("functions", [])
    symbols = ghidra.get("symbols", [])

    function_index = index_entries(functions)
    symbol_index = index_entries(symbols)

    correlations: list[dict[str, Any]] = []
    unmatched_xmap: list[dict[str, Any]] = []
    matched_ghidra_addresses: set[int] = set()
    conflicts: list[dict[str, Any]] = []

    for xmap_symbol in xmap_symbols:
        source_address = address_value(xmap_symbol)
        if source_address is None:
            unmatched_xmap.append({
                "name": xmap_symbol.get("name"),
                "reason": "invalid_address",
            })
            continue

        target_address = source_address + address_offset
        function_candidates = function_index.get(target_address, [])
        symbol_candidates = symbol_index.get(target_address, [])

        if len(function_candidates) > 1:
            conflicts.append({
                "type": "multiple_ghidra_functions_same_address",
                "address": f"0x{target_address:08X}",
                "xmap_name": xmap_symbol.get("name"),
                "candidates": [item.get("name") for item in function_candidates],
            })

        if len(symbol_candidates) > 1:
            conflicts.append({
                "type": "multiple_ghidra_symbols_same_address",
                "address": f"0x{target_address:08X}",
                "xmap_name": xmap_symbol.get("name"),
                "candidates": [item.get("name") for item in symbol_candidates],
            })

        function = function_candidates[0] if function_candidates else None
        primary_symbol = next(
            (item for item in symbol_candidates if item.get("is_primary")),
            symbol_candidates[0] if symbol_candidates else None,
        )

        if function is None and primary_symbol is None:
            unmatched_xmap.append({
                "name": xmap_symbol.get("name"),
                "address": xmap_symbol.get("address"),
                "adjusted_address": f"0x{target_address:08X}",
                "kind": xmap_symbol.get("kind"),
                "reason": "no_ghidra_entry_at_address",
            })
            continue

        matched_ghidra_addresses.add(target_address)
        ghidra_name = function.get("name") if function else primary_symbol.get("name")
        ghidra_kind = "function" if function else "symbol"

        correlations.append({
            "xmap_name": xmap_symbol.get("name"),
            "xmap_address": xmap_symbol.get("address"),
            "xmap_address_int": source_address,
            "xmap_kind": xmap_symbol.get("kind"),
            "xmap_section": xmap_symbol.get("section"),
            "xmap_size": xmap_symbol.get("size"),
            "xmap_inferred_size": xmap_symbol.get("inferred_size"),
            "xmap_size_source": xmap_symbol.get("size_source"),
            "ghidra_name": ghidra_name,
            "ghidra_address": f"0x{target_address:08X}",
            "ghidra_entry_kind": ghidra_kind,
            "ghidra_function": function,
            "ghidra_primary_symbol": primary_symbol,
            "match": {
                "type": "exact_address",
                "address_offset": address_offset,
                "confidence": "high",
            },
        })

    unmatched_ghidra_functions = []
    for function in functions:
        address = address_value(function)
        if address is None:
            continue
        if address not in matched_ghidra_addresses:
            unmatched_ghidra_functions.append({
                "name": function.get("name"),
                "address": function.get("entry"),
                "reason": "no_xmap_symbol_at_address",
            })


    return {
        "format": "xmap-ghidra-correlation-v1",
        "inputs": {
            "xmap_file": xmap.get("file"),
            "ghidra_program": ghidra.get("program", {}).get("name"),
            "address_offset": f"0x{address_offset:X}",
        },
        "statistics": {
            "xmap_symbols": len(xmap_symbols),
            "ghidra_functions": len(functions),
            "ghidra_symbols": len(symbols),
            "correlations": len(correlations),
            "unmatched_xmap": len(unmatched_xmap),
            "conflicts": len(conflicts),
        },
        "correlations": correlations,
        "unmatched_xmap": unmatched_xmap,
        "unmatched_ghidra_functions": unmatched_ghidra_functions,
        "conflicts": conflicts,
        "policy": {
            "address_mapping": "exact_after_explicit_offset",
            "rom_offsets_inferred": False,
            "auto_address_delta": False,
            "semantic_inference_from_names": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correlate parsed XMAP evidence with a Ghidra program export."
    )
    parser.add_argument("xmap_json", type=Path)
    parser.add_argument("ghidra_json", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--address-offset",
        default="0",
        help="Explicit signed address delta applied to XMAP addresses. "
        "Use only when independently validated.",
    )
    args = parser.parse_args()

    xmap = json.loads(args.xmap_json.read_text(encoding="utf-8"))
    ghidra = json.loads(args.ghidra_json.read_text(encoding="utf-8"))
    result = correlate(xmap, ghidra, parse_offset(args.address_offset))

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
