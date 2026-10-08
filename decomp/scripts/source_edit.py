#!/usr/bin/env python3
"""Deterministic UTF-8 source editing helper for decompilation agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


EXIT_USAGE = 2
EXIT_CONFLICT = 3
EXIT_IO = 4
TOOL_TRANSPORT_FAILURE = 5


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_input(project: Path, value: Path) -> Path:
    return value if value.is_absolute() else project / value


def resolve_target(project: Path, target: Path, allow_outside: bool = False) -> Path:
    project_root = project.resolve()
    path = target if target.is_absolute() else project_root / target
    path = path.resolve()
    if not allow_outside:
        try:
            path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(f"Target is outside project: {path}") from exc
    return path


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def expected_hash_ok(path: Path, expected: str | None) -> bool:
    if expected is None:
        return True
    return sha256_bytes(read_bytes(path)) == expected.lower()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_utf8(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_result(
    path: Path,
    before: bytes,
    after: bytes,
    operation: str,
    replacements: int | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": "ok",
        "operation": operation,
        "path": str(path),
        "bytes_before": len(before),
        "bytes_after": len(after),
        "sha256_before": sha256_bytes(before),
        "sha256_after": sha256_bytes(after),
    }
    if replacements is not None:
        payload["replacements"] = replacements
    print(json.dumps(payload, indent=2, sort_keys=True))


def write_file(args: argparse.Namespace) -> int:
    path = resolve_target(args.project, args.path, args.allow_outside_project)
    content_file = resolve_input(args.project, args.content_file)
    if not path.is_file():
        print(f"Target file not found: {path}")
        return EXIT_IO
    before = read_bytes(path)
    if not expected_hash_ok(path, args.expected_sha256):
        print(json.dumps({
            "status": "conflict",
            "reason": "sha256-mismatch",
            "path": str(path),
        }))
        return EXIT_CONFLICT
    after = read_bytes(content_file)
    try:
        after.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"Replacement content is not UTF-8: {content_file}: {exc}")
        return EXIT_IO
    atomic_write(path, after)
    write_result(path, before, after, "write")
    return 0


def replace_text(args: argparse.Namespace) -> int:
    path = resolve_target(args.project, args.path, args.allow_outside_project)
    old_file = resolve_input(args.project, args.old_file)
    new_file = resolve_input(args.project, args.new_file)
    if not path.is_file():
        print(f"Target file not found: {path}")
        return EXIT_IO
    before = read_bytes(path)
    if not expected_hash_ok(path, args.expected_sha256):
        print(json.dumps({
            "status": "conflict",
            "reason": "sha256-mismatch",
            "path": str(path),
        }))
        return EXIT_CONFLICT
    text = before.decode("utf-8")
    old = load_utf8(old_file)
    new = load_utf8(new_file)
    count = text.count(old)
    if count == 0:
        print(json.dumps({
            "status": "conflict",
            "reason": "old-text-not-found",
            "path": str(path),
        }))
        return EXIT_CONFLICT
    if args.max_replacements > 0 and count > args.max_replacements:
        print(json.dumps({
            "status": "conflict",
            "reason": "too-many-matches",
            "path": str(path),
            "matches": count,
            "max_replacements": args.max_replacements,
        }))
        return EXIT_CONFLICT
    limit = args.max_replacements if args.max_replacements > 0 else count
    after = text.replace(old, new, limit).encode("utf-8")
    atomic_write(path, after)
    write_result(path, before, after, "replace-text", min(count, limit))
    return 0


def replace_lines(args: argparse.Namespace) -> int:
    path = resolve_target(args.project, args.path, args.allow_outside_project)
    replacement_file = resolve_input(args.project, args.replacement_file)
    if not path.is_file():
        print(f"Target file not found: {path}")
        return EXIT_IO
    if args.start_line < 1 or args.end_line < args.start_line:
        print("Invalid line range")
        return EXIT_USAGE
    before = read_bytes(path)
    if not expected_hash_ok(path, args.expected_sha256):
        print(json.dumps({
            "status": "conflict",
            "reason": "sha256-mismatch",
            "path": str(path),
        }))
        return EXIT_CONFLICT
    text = before.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if args.end_line > len(lines):
        print(json.dumps({
            "status": "conflict",
            "reason": "line-range-out-of-bounds",
            "path": str(path),
            "line_count": len(lines),
        }))
        return EXIT_CONFLICT
    replacement = load_utf8(replacement_file)
    updated = "".join(
        lines[: args.start_line - 1] + [replacement] + lines[args.end_line:]
    )
    after = updated.encode("utf-8")
    atomic_write(path, after)
    write_result(
        path,
        before,
        after,
        "replace-lines",
        args.end_line - args.start_line + 1,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--allow-outside-project", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="Replace a complete existing UTF-8 file.")
    write.add_argument("--path", type=Path, required=True)
    write.add_argument("--content-file", type=Path, required=True)
    write.add_argument("--expected-sha256")
    write.set_defaults(handler=write_file)

    replace = sub.add_parser(
        "replace-text",
        help="Replace exact UTF-8 text from files.",
    )
    replace.add_argument("--path", type=Path, required=True)
    replace.add_argument("--old-file", type=Path, required=True)
    replace.add_argument("--new-file", type=Path, required=True)
    replace.add_argument("--expected-sha256")
    replace.add_argument("--max-replacements", type=int, default=1)
    replace.set_defaults(handler=replace_text)

    lines = sub.add_parser(
        "replace-lines",
        help="Replace an inclusive line range from a UTF-8 file.",
    )
    lines.add_argument("--path", type=Path, required=True)
    lines.add_argument("--start-line", type=int, required=True)
    lines.add_argument("--end-line", type=int, required=True)
    lines.add_argument("--replacement-file", type=Path, required=True)
    lines.add_argument("--expected-sha256")
    lines.set_defaults(handler=replace_lines)

    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"tool-transport-failure: {exc}")
        return TOOL_TRANSPORT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
