#!/usr/bin/env python3
"""Validate the directory and helper-path conventions used by decomp skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^(?=.{1,64}$)(?!.*--)[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")

    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")

    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


def validate_skill(path: Path, skills_root: Path) -> list[str]:
    errors: list[str] = []
    folder_name = path.parent.name

    try:
        content = path.read_text(encoding="utf-8")
        metadata = parse_frontmatter(content)
    except (OSError, ValueError) as exc:
        return [f"{path}: {exc}"]

    skill_name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not skill_name:
        errors.append(f"{path}: missing name")
    elif skill_name != folder_name:
        errors.append(
            f"{path}: name {skill_name!r} does not match directory {folder_name!r}"
        )
    elif not NAME_RE.fullmatch(skill_name):
        errors.append(f"{path}: invalid portable skill name {skill_name!r}")

    if not description:
        errors.append(f"{path}: missing description")

    if "<skills>/decomp/scripts" in content:
        errors.append(f"{path}: host-specific <skills> helper path remains")

    if "decomp/scripts/" in content:
        errors.append(f"{path}: repository-root helper path remains; use ../../scripts/")

    if "/path/to/skills/decomp/scripts" in content:
        errors.append(f"{path}: example-only absolute helper path remains")

    for relative in re.findall(
        r"(?<![A-Za-z0-9_.-])\.\./\.\./scripts/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", content
    ):
        helper = (path.parent / relative).resolve()
        if not helper.is_file():
            errors.append(
                f"{path}: helper path does not exist: {relative} -> {helper}"
            )

    if path.parent.parent != skills_root:
        errors.append(f"{path}: unexpected skill nesting")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    skills_root = repo_root / "skills"
    skill_files = sorted(skills_root.rglob("SKILL.md"))

    if not skill_files:
        print("No SKILL.md files found.", file=sys.stderr)
        return 1

    errors: list[str] = []
    skill_names: dict[str, Path] = {}
    for path in skill_files:
        errors.extend(validate_skill(path, skills_root))
        try:
            metadata = parse_frontmatter(path.read_text(encoding="utf-8"))
            name = metadata.get("name", "")
        except (OSError, ValueError):
            name = ""
        if name:
            previous = skill_names.get(name)
            if previous is not None:
                errors.append(
                    f"{path}: duplicate skill name {name!r}; already defined by {previous}"
                )
            else:
                skill_names[name] = path

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"Validated {len(skill_files)} decomp skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
