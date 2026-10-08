#!/usr/bin/env python3
"""Detect the correct Ghidra launcher for headless and PyGhidra workflows."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def launcher_info(ghidra_home: Path | None = None) -> dict[str, str | bool | None]:
    homes: list[Path] = []
    if ghidra_home:
        homes.append(ghidra_home.expanduser().resolve())

    env_home = os.environ.get("GHIDRA_HOME")
    if env_home:
        homes.append(Path(env_home).expanduser().resolve())

    path_py = shutil.which("pyghidraRun")
    path_py_bat = shutil.which("pyghidraRun.bat")
    path_headless = shutil.which("analyzeHeadless")
    path_headless_bat = shutil.which("analyzeHeadless.bat")

    for candidate in (path_py, path_py_bat):
        if candidate:
            p = Path(candidate).resolve()
            homes.append(p.parent.parent)

    for candidate in (path_headless, path_headless_bat):
        if candidate:
            p = Path(candidate).resolve()
            homes.append(p.parent.parent)

    seen: set[Path] = set()
    for home in homes:
        if home in seen:
            continue
        seen.add(home)
        support = home / "support"
        py_candidates = [support / "pyghidraRun.bat", support / "pyghidraRun"]
        headless_candidates = [
            support / "analyzeHeadless.bat",
            support / "analyzeHeadless",
        ]
        py = next((item for item in py_candidates if item.is_file()), None)
        headless = next((item for item in headless_candidates if item.is_file()), None)
        if py or headless:
            return {
                "ghidra_home": str(home),
                "pyghidra_launcher": str(py) if py else None,
                "analyze_headless": str(headless) if headless else None,
                "pyghidra_available": bool(py),
                "headless_available": bool(headless),
            }

    return {
        "ghidra_home": None,
        "pyghidra_launcher": path_py_bat or path_py,
        "analyze_headless": path_headless_bat or path_headless,
        "pyghidra_available": bool(path_py_bat or path_py),
        "headless_available": bool(path_headless_bat or path_headless),
    }


def script_runtime(script: Path) -> str:
    text = script.read_text(encoding="utf-8", errors="replace").lower()
    if "decomp-runtime: pyghidra" in text:
        return "pyghidra"
    if "import pyghidra" in text or "from pyghidra" in text:
        return "pyghidra"
    return "ghidra-headless"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("detect", "script-runtime"))
    parser.add_argument("--ghidra-home", type=Path)
    parser.add_argument("--script", type=Path)
    parser.add_argument("--require-pyghidra", action="store_true")
    args = parser.parse_args()

    if args.command == "detect":
        result = launcher_info(args.ghidra_home)
        if args.require_pyghidra and not result["pyghidra_available"]:
            print(json.dumps(result, indent=2, sort_keys=True))
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if not args.script:
        parser.error("script-runtime requires --script")

    if not args.script.is_file():
        parser.error(f"script not found: {args.script}")

    print(script_runtime(args.script))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
