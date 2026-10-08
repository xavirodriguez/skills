#!/usr/bin/env python3
"""Index source definitions for matching-decomp candidate classification."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CPP_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx"}


FUNCTION_RE = re.compile(
    r"(?m)^[ \t]*(?:(?:ARM|THUMB)[ \t]+)?(?:[A-Za-z_~][\w:<>,*&\[\] \t]*?[ \t]+)?"
    r"(?P<name>[A-Za-z_~][\w:~]*)(?:<[^;\n{}]*>)?[ \t]*\([^;\n{}]*\)[ \t]*(?:const[ \t]*)?"
    r"(?:\{|$)"
)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name)


def index_sources(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for base in (root / "src", root / "libs"):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in CPP_EXTENSIONS:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            text = "\n".join(lines)
            for match in FUNCTION_RE.finditer(text):
                name = match.group("name")
                if name in {"if", "for", "while", "switch", "catch"}:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                key = normalize_name(name)
                result.setdefault(key, {
                    "name": name,
                    "source_file": str(path),
                    "line": line,
                })
    return result


def lookup(index: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    direct = index.get(normalize_name(name))
    if direct:
        return direct

    # objdiff symbols can be mangled while source uses a C++ definition.
    demangled = name.split("::", 1)[-1] if "::" in name else name
    return index.get(normalize_name(demangled))
