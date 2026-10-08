#!/usr/bin/env python3
"""Validate structured integration evidence for decompilation targets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXIT_INVALID = 4


def parse_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer/address")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 16)
            except ValueError as exc:
                raise ValueError(f"{field} is not a valid address/integer: {value}") from exc
    raise ValueError(f"{field} must be an integer/address")


def validate_region(name: str, region: Any) -> dict[str, Any]:
    if not isinstance(region, dict):
        raise ValueError(f"region {name!r} must be an object")

    function = region.get("function")
    obj = region.get("object")
    rng = region.get("range")
    evidence = region.get("evidence")
    verification = region.get("verification")

    if not isinstance(function, dict):
        raise ValueError(f"region {name!r} is missing function metadata")
    if not isinstance(obj, dict):
        raise ValueError(f"region {name!r} is missing object metadata")
    if not isinstance(rng, dict):
        raise ValueError(f"region {name!r} is missing range metadata")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"region {name!r} needs independent evidence")
    if not isinstance(verification, dict):
        raise ValueError(f"region {name!r} needs authoritative verification")
    verification_status = str(verification.get("status") or "").lower()
    if verification_status != "pass":
        raise ValueError(f"region {name!r} authoritative verification is not pass")
    try:
        verification_match = float(verification.get("function_match_percent"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"region {name!r} needs numeric function match verification") from exc
    if verification_match < 100.0:
        raise ValueError(f"region {name!r} authoritative function match is below 100%")
    verification_command = str(verification.get("command") or "").strip()
    if not verification_command:
        raise ValueError(f"region {name!r} needs authoritative verification command")

    object_name = str(obj.get("name") or "").strip()
    if not object_name:
        raise ValueError(f"region {name!r} needs object name")

    function_entry = parse_int(function.get("entry"), f"{name}.function.entry")
    function_size = parse_int(function.get("size"), f"{name}.function.size")
    object_start = parse_int(obj.get("start"), f"{name}.object.start")
    object_end = parse_int(obj.get("end"), f"{name}.object.end")
    range_start = parse_int(rng.get("start"), f"{name}.range.start")
    range_end = parse_int(rng.get("end"), f"{name}.range.end")

    if function_size < 1:
        raise ValueError(f"{name}.function.size must be > 0")
    if object_end < object_start:
        raise ValueError(f"{name}.object range is reversed")
    if range_end < range_start:
        raise ValueError(f"{name}.range is reversed")
    function_end = function_entry + function_size - 1
    if not object_start <= function_entry <= object_end:
        raise ValueError(f"{name}.function.entry is outside object range")
    if not range_start <= function_entry <= range_end:
        raise ValueError(f"{name}.function.entry is outside integration range")
    if function_end > object_end:
        raise ValueError(f"{name}.function extends past object end")
    if function_end > range_end:
        raise ValueError(f"{name}.function extends past integration range")

    padding = region.get("padding", {})
    if not isinstance(padding, dict):
        raise ValueError(f"{name}.padding must be an object")

    normalized_padding: dict[str, list[dict[str, int]]] = {}
    for side in ("before", "after"):
        entries = padding.get(side, [])
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            raise ValueError(f"{name}.padding.{side} must be a list")
        normalized: list[dict[str, int]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"{name}.padding.{side}[{index}] must be an object")
            start = parse_int(entry.get("start"), f"{name}.padding.{side}[{index}].start")
            end = parse_int(entry.get("end"), f"{name}.padding.{side}[{index}].end")
            if end < start:
                raise ValueError(f"{name}.padding.{side}[{index}] is reversed")
            normalized.append({"start": start, "end": end, "bytes": end - start + 1})
        normalized_padding[side] = normalized

    return {
        "function": {
            "entry": function_entry,
            "size": function_size,
            "end": function_end,
        },
        "object": {
            "name": object_name,
            "start": object_start,
            "end": object_end,
        },
        "range": {
            "kind": str(rng.get("kind") or "delink"),
            "start": range_start,
            "end": range_end,
        },
        "padding": normalized_padding,
        "next_boundary": (
            parse_int(region["next_boundary"], f"{name}.next_boundary")
            if region.get("next_boundary") is not None
            else None
        ),
        "evidence": [str(item) for item in evidence],
        "verification": {
            "status": "pass",
            "function_match_percent": verification_match,
            "command": verification_command,
        },
        "independent_evidence": bool(region.get("independent_evidence", True)),
    }


def validate_document(payload: dict[str, Any], target: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("integration evidence must be an object")

    actual_target = str(payload.get("target") or target or "").strip()
    if not actual_target:
        raise ValueError("integration evidence needs target")

    regions = payload.get("regions")
    if not isinstance(regions, dict) or not regions:
        raise ValueError("integration evidence needs at least one region")

    normalized_regions = {
        str(name): validate_region(str(name), region)
        for name, region in regions.items()
    }

    if len(normalized_regions) > 1:
        missing = [
            name
            for name, region in normalized_regions.items()
            if not region["independent_evidence"]
        ]
        if missing:
            raise ValueError(
                "regional integration changes require independent evidence: "
                + ", ".join(sorted(missing))
            )

    return {
        "format": "decomp-integration-evidence-v1",
        "target": actual_target,
        "regions": normalized_regions,
        "summary": {
            "region_count": len(normalized_regions),
            "function_entries": {
                name: region["function"]["entry"]
                for name, region in normalized_regions.items()
            },
            "object_ranges": {
                name: {
                    "start": region["object"]["start"],
                    "end": region["object"]["end"],
                }
                for name, region in normalized_regions.items()
            },
            "integration_ranges": {
                name: {
                    "kind": region["range"]["kind"],
                    "start": region["range"]["start"],
                    "end": region["range"]["end"],
                }
                for name, region in normalized_regions.items()
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_json", type=Path)
    parser.add_argument("--target")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        normalized = validate_document(payload, args.target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "invalid-integration-evidence",
            "reason": str(exc),
        }, indent=2, sort_keys=True))
        return EXIT_INVALID

    rendered = json.dumps(normalized, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
