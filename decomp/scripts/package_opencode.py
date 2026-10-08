#!/usr/bin/env python3
"""Build a self-contained OpenCode skill bundle from the canonical decomp tree."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_PATH_REPLACEMENT = "../../scripts/"


def package_skills(source_root: Path, output_root: Path, force: bool) -> dict[str, object]:
    skills_root = source_root / "skills"
    if not skills_root.is_dir():
        raise FileNotFoundError(f"Skills root does not exist: {skills_root}")

    if output_root.exists():
        if not force:
            raise FileExistsError(
                f"Output exists: {output_root}. Use --force to replace it."
            )
        shutil.rmtree(output_root)

    output_root.mkdir(parents=True)

    packaged: list[str] = []
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue

        destination = output_root / skill_dir.name
        shutil.copytree(skill_dir, destination)
        content = (destination / "SKILL.md").read_text(encoding="utf-8")
        content = content.replace(
            SKILL_PATH_REPLACEMENT,
            "../_runtime/",
        )
        (destination / "SKILL.md").write_text(content, encoding="utf-8")
        packaged.append(skill_dir.name)

    runtime = output_root / "_runtime"
    scripts_source = source_root / "scripts"
    shutil.copytree(
        scripts_source,
        runtime,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "tests",
            "README.md",
        ),
    )

    manifest = {
        "format": "decomp-opencode-bundle-v1",
        "source": str(source_root.resolve()),
        "output": str(output_root.resolve()),
        "skills": packaged,
        "runtime": "_runtime",
        "helper_path_rewrite": {
            "../../scripts/": "../_runtime/",
        },
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="The decomp directory containing skills/ and scripts/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory to expose as an OpenCode skills source.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = package_skills(
        args.source_root.resolve(),
        args.output.resolve(),
        args.force,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
