#!/usr/bin/env python3
"""Read-only project inspector for matching-decomp workflows."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BUILD_FILES = ("Makefile", "makefile", "GNUmakefile", "CMakeLists.txt", "build.ninja", "meson.build")
CONFIG_FILES = ("objdiff.json", "decomp.me", "decomp.yaml", "decomp.yml", "config.mk", "config.py")
STATUS_DIRS = ("asm/nonmatchings", "asm/matchings", "nonmatchings", "matchings")
SOURCE_DIRS = ("src", "source", "srcs", "include")

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

def signal_lines(content: str, patterns: list[str], limit: int = 8) -> list[str]:
    out = []
    for number, line in enumerate(content.splitlines(), 1):
        if any(re.search(pattern, line, re.I) for pattern in patterns):
            out.append(f"{number}: {line.strip()}")
            if len(out) >= limit:
                break
    return out

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"Not a directory: {root}"}, indent=2))
        return 2

    files = []
    for name in BUILD_FILES + CONFIG_FILES + ("README.md", "README", "AGENTS.md"):
        if (root / name).is_file():
            files.append(name)

    status = {}
    for directory in STATUS_DIRS:
        path = root / directory
        if path.is_dir():
            try:
                status[directory] = sum(1 for item in path.rglob("*") if item.is_file())
            except OSError:
                status[directory] = None

    source_count = 0
    for directory in SOURCE_DIRS:
        path = root / directory
        if path.is_dir():
            try:
                source_count += sum(
                    1 for item in path.rglob("*")
                    if item.suffix in {".c", ".h", ".cpp", ".hpp", ".s", ".inc"}
                )
            except OSError:
                pass

    evidence = []
    patterns = [
        r"compare", r"objdiff", r"nonmatch", r"matchings?", r"agbcc",
        r"clang", r"gcc", r"arm-none-eabi", r"mips", r"powerpc", r"thumb", r"rom",
    ]
    for name in files:
        hits = signal_lines(read_text(root / name), patterns)
        if hits:
            evidence.append({"file": name, "signals": hits})

    print(json.dumps({
        "project_root": str(root),
        "build_files": [x for x in files if x in BUILD_FILES],
        "config_files": [x for x in files if x in CONFIG_FILES],
        "documentation_files": [x for x in files if x in {"README.md", "README", "AGENTS.md"}],
        "status_directories": status,
        "source_file_count": source_count,
        "signals": evidence,
        "next_steps": [
            "Read the authoritative README/build configuration.",
            "Identify the exact build and comparison commands.",
            "Identify how matching/nonmatching functions are represented.",
            "Identify compiler, flags, architecture and translation-unit layout.",
            "Only then scout and analyze a target.",
        ],
    }, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
