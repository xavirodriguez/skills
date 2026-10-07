#!/usr/bin/env python3
"""Index an existing decompilation project as reference evidence.

The scanner recognizes common decomp-project annotations such as
"// non-matching" and function names that encode addresses, for example
func_0203c72c or func_ov014_02144820.

An unmarked function is only "apparently matching": it is useful for avoiding
duplicate work, but it is not proof of an exact machine-code match.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CPP_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}

FUNCTION_NAME_RE = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\("
)
ADDRESS_RE = re.compile(r"(?:^|_)(?P<address>[0-9A-Fa-f]{8})$")
MARKER_RE = re.compile(
    r"^\s*//\s*non-matching(?:\s*\((?P<reason>[^)]+)\))?\s*$", re.I
)
MODE_RE = re.compile(r"\b(?P<mode>ARM|THUMB)\b")
CONTROL_NAMES = {
    "if", "for", "while", "switch", "catch", "sizeof", "return",
    "static_assert", "decltype",
}


def function_address(name: str) -> int | None:
    match = ADDRESS_RE.search(name)
    return int(match.group("address"), 16) if match else None


def find_function_name(text: str) -> str | None:
    names = [match.group("name") for match in FUNCTION_NAME_RE.finditer(text)]
    names = [name for name in names if name not in CONTROL_NAMES]
    return names[-1] if names else None


def parse_marker(line: str) -> tuple[str, str | None] | None:
    match = MARKER_RE.match(line)
    if match is None:
        return None
    reason = match.group("reason")
    reason = reason.strip() if reason else None
    if reason and reason.lower() == "equivalent":
        return "known_nonmatching_equivalent", reason
    return "known_nonmatching", reason


def looks_like_definition(signature: str) -> bool:
    if "{" not in signature or ";" in signature.split("{", 1)[0]:
        return False
    return find_function_name(signature) is not None


def scan_source_file(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries: list[dict[str, Any]] = []
    pending_status: tuple[str, str | None] | None = None
    buffer: list[str] = []

    for line_number, line in enumerate(lines, 1):
        marker = parse_marker(line)
        if marker is not None:
            pending_status = marker
            buffer = []
            continue

        if not buffer and not line.strip():
            continue

        buffer.append(line)
        if len(buffer) > 24:
            buffer.pop(0)

        candidate = "\n".join(buffer)
        if not looks_like_definition(candidate):
            if candidate.rstrip().endswith(";") or "}" in candidate:
                buffer = []
            continue

        name = find_function_name(candidate)
        if name is None:
            buffer = []
            continue

        mode_match = MODE_RE.search(candidate)
        address = function_address(name)
        status = pending_status[0] if pending_status else "unmarked"
        reason = pending_status[1] if pending_status else None

        if status == "unmarked":
            action = "skip_by_default"
            confidence = "medium"
            note = (
                "No non-matching marker was found immediately before the definition. "
                "Treat as apparently matching, not as exact-match proof."
            )
        elif status == "known_nonmatching_equivalent":
            action = "reuse_reference_fix_codegen"
            confidence = "high"
            note = (
                "Reference project marks this implementation equivalent but non-matching; "
                "reuse its semantics and focus on machine-code/codegen differences."
            )
        else:
            action = "reuse_reference_and_match"
            confidence = "high"
            note = (
                "Reference project explicitly marks this function as non-matching; "
                "reuse its implementation/context instead of starting from scratch."
            )

        entries.append({
            "name": name,
            "address": f"0x{address:08X}" if address is not None else None,
            "address_int": address,
            "source_file": str(path),
            "line": line_number,
            "mode": mode_match.group("mode") if mode_match else None,
            "status": status,
            "status_reason": reason,
            "recommended_action": action,
            "confidence": confidence,
            "status_note": note,
        })
        buffer = []
        pending_status = None

    return entries


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def correlate_reference(
    functions: list[dict[str, Any]],
    xmap: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_address: dict[int, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}

    for function in functions:
        address = function.get("address_int")
        if isinstance(address, int):
            by_address.setdefault(address, []).append(function)
        by_name.setdefault(function["name"], []).append(function)

    matches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    if xmap is None:
        return matches, unmatched

    for symbol in xmap.get("symbols", []):
        address = symbol.get("address_int")
        name = symbol.get("name")
        candidates = by_address.get(address, []) if isinstance(address, int) else []

        if not candidates and isinstance(name, str):
            candidates = by_name.get(name, [])

        if not candidates:
            unmatched.append({
                "xmap_name": name,
                "xmap_address": symbol.get("address"),
                "reason": "no_reference_function",
            })
            continue

        for candidate in candidates:
            identity = (
                "exact_address"
                if isinstance(address, int)
                and candidate.get("address_int") == address
                else "exact_name"
            )
            confidence = "high" if identity == "exact_address" else "medium"
            matches.append({
                "xmap_name": name,
                "xmap_address": symbol.get("address"),
                "reference_name": candidate["name"],
                "reference_address": candidate.get("address"),
                "reference_file": candidate["source_file"],
                "reference_line": candidate["line"],
                "reference_mode": candidate.get("mode"),
                "reference_status": candidate["status"],
                "reference_status_reason": candidate.get("status_reason"),
                "reference_recommended_action": candidate["recommended_action"],
                "identity": identity,
                "confidence": confidence,
            })

    return matches, unmatched


def analyze(root: Path, xmap: dict[str, Any] | None) -> dict[str, Any]:
    source_roots = [root / "src", root / "libs"]
    files = [
        path
        for base in source_roots
        if base.is_dir()
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in CPP_EXTENSIONS
    ]

    functions: list[dict[str, Any]] = []
    for path in sorted(files):
        functions.extend(scan_source_file(path))

    status_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for function in functions:
        status = function["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        action = function["recommended_action"]
        action_counts[action] = action_counts.get(action, 0) + 1

    matches, unmatched = correlate_reference(functions, xmap)

    return {
        "format": "reference-decomp-analysis-v2",
        "project": {
            "path": str(root),
            "name": root.name,
            "expected_repo": "https://github.com/zeldaret/ph",
        },
        "statistics": {
            "source_files": len(files),
            "functions": len(functions),
            "status_counts": status_counts,
            "recommended_action_counts": action_counts,
            "xmap_matches": len(matches),
            "xmap_unmatched": len(unmatched),
        },
        "functions": functions,
        "xmap_matches": matches,
        "xmap_unmatched": unmatched,
        "policy": {
            "reference_repo_is_context_not_authority": True,
            "unmarked_is_apparently_matching_not_proof": True,
            "nonmatching_marker_is_explicit_evidence": True,
            "exact_address_preferred_over_name": True,
            "skip_apparently_matching_without_authoritative_mismatch": True,
            "reference_build_report_can_upgrade_status": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index a local reference decompilation project."
    )
    parser.add_argument("project", type=Path)
    parser.add_argument("--xmap", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    xmap = load_json(args.xmap) if args.xmap else None
    result = analyze(args.project.resolve(), xmap)
    rendered = json.dumps(result, indent=2, sort_keys=True)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
