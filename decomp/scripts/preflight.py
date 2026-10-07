#!/usr/bin/env python3
"""Cross-platform decompilation environment and project preflight."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def command_path(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def python_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for name in ("py", "python", "python3"):
        path = shutil.which(name)
        if not path:
            continue
        if os.name == "nt" and "WindowsApps" in path:
            candidates.append({
                "name": name,
                "path": path,
                "usable": False,
                "reason": "Windows Store execution alias",
            })
            continue
        candidates.append({"name": name, "path": path, "usable": True})
    current = os.path.abspath(os.sys.executable)
    if not any(item.get("path") == current for item in candidates):
        candidates.insert(0, {"name": "current", "path": current, "usable": True})
    return candidates


def detect_shell() -> dict[str, str | None]:
    if os.name != "nt":
        return {
            "family": "posix",
            "name": os.environ.get("SHELL"),
            "recommended": "bash",
        }

    ps_version = None
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            ps_version = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    pwsh = command_path("pwsh", "pwsh.exe")
    powershell = command_path("powershell", "powershell.exe")
    return {
        "family": "windows",
        "name": "PowerShell",
        "version": ps_version,
        "recommended": "pwsh" if pwsh else ("powershell" if powershell else None),
    }


def ghidra_headless_path() -> str | None:
    from_env = os.environ.get("GHIDRA_HOME")
    if from_env:
        base = Path(from_env)
        for name in ("analyzeHeadless.bat", "analyzeHeadless"):
            candidate = base / "support" / name
            if candidate.exists():
                return str(candidate)
            candidate = base / "bin" / name
            if candidate.exists():
                return str(candidate)
    return command_path("analyzeHeadless", "analyzeHeadless.bat", "analyzeHeadless.bat.exe")


def tool_checks() -> dict[str, Any]:
    return {
        "git": command_path("git", "git.exe"),
        "ninja": command_path("ninja", "ninja.exe"),
        "make": command_path("make", "make.exe"),
        "objdiff": command_path("objdiff", "objdiff.exe"),
        "objdiff_cli": command_path("objdiff-cli", "objdiff-cli.exe"),
        "ghidra_headless": ghidra_headless_path(),
    }


def project_checks(root: Path, reference: Path | None, xmap: Path | None) -> dict[str, Any]:
    paths = {
        "project": root,
        "objdiff_json": root / "objdiff.json",
        "build_ninja": root / "build.ninja",
        "configure_py": root / "tools" / "configure.py",
        "arm9_xmap": xmap if xmap else None,
        "reference_project": reference if reference else None,
    }
    return {
        name: {
            "path": str(path) if path else None,
            "exists": bool(path and path.exists()),
            "is_file": bool(path and path.is_file()),
            "is_dir": bool(path and path.is_dir()),
        }
        for name, path in paths.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--xmap", type=Path)
    args = parser.parse_args()

    root = args.project.resolve()
    reference = args.reference.resolve() if args.reference else None
    xmap = args.xmap.resolve() if args.xmap else None

    python_info = python_candidates()
    tools = tool_checks()
    shell = detect_shell()
    checks = project_checks(root, reference, xmap)

    blockers: list[str] = []
    usable_python = next((item for item in python_info if item["usable"]), None)
    if usable_python is None:
        blockers.append("No usable Python interpreter found.")
    if not root.is_dir():
        blockers.append(f"Target project does not exist: {root}")

    result = {
        "format": "decomp-preflight-v1",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "shell": shell,
        "python_candidates": python_info,
        "recommended_python": usable_python,
        "tools": tools,
        "project": checks,
        "blockers": blockers,
        "status": "blocked" if blockers else "ready",
        "policy": {
            "shell_commands_must_match_detected_shell": True,
            "never_use_bash_syntax_in_powershell": True,
            "never_assume_python3_on_windows": True,
            "never_claim_match_when_environment_is_blocked": True,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
