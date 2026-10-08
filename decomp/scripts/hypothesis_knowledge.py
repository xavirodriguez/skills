#!/usr/bin/env python3
"""Search the decompilation hypothesis ledger for reusable prior lessons."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STOP_WORDS = {
    "a", "an", "and", "as", "at", "before", "by", "change", "code", "for",
    "from", "in", "into", "is", "match", "of", "on", "or", "same", "source",
    "target", "the", "to", "with", "use", "using", "when", "one",
}


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if token not in STOP_WORDS and len(token) > 1
    }


def read_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def search(
    entries: list[dict[str, Any]],
    *,
    target: str = "",
    query: str = "",
    tags: list[str] | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    query_tokens = tokens(query)
    target_tokens = tokens(target)
    tag_set = {tag.lower() for tag in (tags or [])}
    ranked: list[tuple[float, dict[str, Any]]] = []

    for entry in entries:
        entry_target = str(entry.get("target", ""))
        entry_text = " ".join(
            str(entry.get(key, ""))
            for key in ("target", "hypothesis", "source_change", "lesson", "decision")
        )
        entry_tokens = tokens(entry_text)
        entry_tags = {
            str(tag).lower()
            for tag in entry.get("mismatch_tags", [])
            if tag is not None
        }

        score = 0.0
        reasons: list[str] = []

        shared_query = query_tokens & entry_tokens
        if shared_query:
            score += len(shared_query) * 3.0
            reasons.append(f"query:{','.join(sorted(shared_query))}")

        shared_target = target_tokens & tokens(entry_target)
        if shared_target:
            score += len(shared_target) * 1.5

        shared_tags = tag_set & entry_tags
        if shared_tags:
            score += len(shared_tags) * 6.0
            reasons.append(f"tags:{','.join(sorted(shared_tags))}")

        if entry.get("exact_match_after"):
            score += 12.0
            reasons.append("exact-match")

        before = entry.get("match_before")
        after = entry.get("match_after")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = float(after) - float(before)
            if delta > 0:
                score += min(10.0, delta / 10.0)
                reasons.append(f"improved:{delta:+.2f}pp")

        if score <= 0:
            continue

        result = dict(entry)
        result["knowledge_score"] = round(score, 3)
        result["knowledge_reasons"] = reasons
        ranked.append((score, result))

    ranked.sort(
        key=lambda item: (
            -item[0],
            -float(item[1].get("match_after") or 0),
            str(item[1].get("target", "")),
        )
    )
    return [item for _, item in ranked[: max(0, top_k)]]


def compact(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "target": item.get("target"),
            "hypothesis": item.get("hypothesis"),
            "lesson": item.get("lesson"),
            "decision": item.get("decision"),
            "match_before": item.get("match_before"),
            "match_after": item.get("match_after"),
            "first_mismatch": item.get("first_mismatch_after"),
            "mismatch_tags": item.get("mismatch_tags", []),
            "knowledge_score": item.get("knowledge_score"),
            "knowledge_reasons": item.get("knowledge_reasons", []),
        }
        for item in results
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--target", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    results = search(
        read_entries(args.ledger),
        target=args.target,
        query=args.query,
        tags=args.tag,
        top_k=args.top,
    )
    rendered = json.dumps(compact(results), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
