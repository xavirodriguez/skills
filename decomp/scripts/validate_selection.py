#!/usr/bin/env python3
"""Validate that a selection artifact was generated from the supplied inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"not a JSON object: {path}")
    return value


def validate(selection: dict[str, Any], *, report: Path, scout: Path | None, reference: Path | None) -> dict[str, Any]:
    provenance = selection.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("format") != "decomp-selection-provenance-v1":
        raise ValueError("selection artifact has no supported provenance; regenerate it")
    expected = {"report": report}
    if scout is not None:
        expected["scout"] = scout
    if reference is not None:
        expected["reference"] = reference
    mismatches: list[str] = []
    for key, path in expected.items():
        item = provenance.get(key)
        if not isinstance(item, dict):
            mismatches.append(f"missing provenance: {key}")
            continue
        actual_hash = sha256(path.resolve())
        if item.get("sha256") != actual_hash:
            mismatches.append(f"stale provenance: {key}")
    if mismatches:
        raise ValueError("; ".join(mismatches))
    return {
        "status": "valid",
        "selection": selection.get("format"),
        "report_sha256": provenance["report"]["sha256"],
        "scout_sha256": provenance.get("scout", {}).get("sha256"),
        "reference_sha256": provenance.get("reference", {}).get("sha256"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection_json", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--scout", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    try:
        result = validate(
            load(args.selection_json),
            report=args.report,
            scout=args.scout,
            reference=args.reference,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "reason": str(exc)}, indent=2, sort_keys=True))
        return 4
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
