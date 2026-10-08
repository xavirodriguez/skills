#!/usr/bin/env python3
"""Prepare a compact, auditable candidate pack for a decompilation function."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from hypothesis_knowledge import compact, read_entries, search


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_input(project: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path.resolve()
    candidate = (project / path).resolve()
    if candidate.exists():
        return candidate
    fallback = path.resolve()
    return fallback if fallback.exists() else None
def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "candidate"


def resolve_source(project: Path, candidate: dict[str, Any]) -> Path | None:
    source = candidate.get("source")
    if isinstance(source, dict):
        source = source.get("source_file")
    if not isinstance(source, str):
        source = candidate.get("source_path")
    if not isinstance(source, str):
        return None

    path = Path(source)
    options = [path, project / source, project / source.lstrip("./")]
    for option in options:
        if option.is_file():
            return option.resolve()
    return None


def copy_direct_includes(source: Path, project: Path, destination: Path) -> list[str]:
    text = source.read_text(encoding="utf-8", errors="replace")
    includes = re.findall(r'^\s*#include\s+"([^"]+)"', text, re.MULTILINE)
    copied: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)

    roots = [source.parent, project / "include", project / "src", project / "libs"]
    for include in includes:
        found = None
        for root in roots:
            candidate = (root / include).resolve()
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            continue
        target = destination / found.name
        shutil.copy2(found, target)
        copied.append(target.name)
    return copied




def make_prompt(
    candidate: dict[str, Any],
    prior_knowledge: list[dict[str, Any]] | None = None,
) -> str:
    scout = candidate.get("scout", {})
    reference = candidate.get("reference") or {}
    knowledge = prior_knowledge or []
    knowledge_lines = []
    for item in compact(knowledge)[:5]:
        knowledge_lines.append(
            "- {target}: {hypothesis} -> {lesson}".format(
                target=item.get("target"),
                hypothesis=item.get("hypothesis"),
                lesson=item.get("lesson"),
            )
        )
    prior_lessons = "\n".join(knowledge_lines) if knowledge_lines else "- None available."

    values = {
        "name": candidate.get("name"),
        "function_entry": candidate.get("function_entry", candidate.get("address")),
        "function_size": candidate.get("function_size", candidate.get("size")),
        "translation_unit": candidate.get("translation_unit", candidate.get("unit")),
        "match": candidate.get("match_percent"),
        "p75": candidate.get("p75_bytes"),
        "threshold": candidate.get("threshold_bytes"),
        "success": candidate.get("success_score"),
        "logic": candidate.get("game_logic_score"),
        "instructions": scout.get("instructions"),
        "blocks": scout.get("blocks"),
        "conditional": scout.get("conditional_branches", 0),
        "back_edges": scout.get("back_edges", 0),
        "computed": scout.get("computed_jumps", 0),
        "stores": scout.get("stores", scout.get("has_store", 0)),
        "callers": scout.get("callers"),
        "callees": scout.get("callees"),
        "globals": scout.get("globals"),
        "signature": scout.get("signature", ""),
        "reference_action": reference.get("recommended_action"),
        "prior_lessons": prior_lessons,
    }
    return """# Decomp candidate: {name}

This pack was generated from the current authoritative objdiff report.

Target:
- symbol: {name}
- function entry: {function_entry}
- function size: {function_size} bytes
- translation unit: {translation_unit}
- current match: {match}%
- remaining undecompiled P75: {p75} bytes
- Tier 2 threshold: {threshold} bytes
- success score: {success}/100
- game-logic score: {logic}/100

CFG evidence:
- instructions: {instructions}
- basic blocks: {blocks}
- conditional branches: {conditional}
- back edges/loops: {back_edges}
- computed jumps/switches: {computed}
- stores: {stores}
- callers: {callers}
- callees: {callees}
- globals: {globals}
- signature: {signature}

Reference action: {reference_action}

Prior lessons from previous functions:
{prior_lessons}

Work:
1. Verify the function is real game logic and not a getter, stub, wrapper, initializer or table/data helper.
2. Read the supplied source and evidence.
3. Read the supplied compare.json/report evidence and diagnose the first mismatch.
4. Make one source-level hypothesis/change.
5. Build and run the project's authoritative comparison.
6. Record the result in .decomp-agent/hypotheses.jsonl.
7. Repeat until exact match or a concrete blocker.

Only exact machine-code matching counts as success.
""".format(**values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection_json", type=Path)
    parser.add_argument("candidate", help="Exact candidate symbol/name.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--compare-json", type=Path, help="Existing non-interactive compare_target.py result for this candidate.")
    parser.add_argument("--scout-json", type=Path)
    parser.add_argument("--analysis-json", type=Path)
    parser.add_argument("--reference-json", type=Path)
    parser.add_argument("--xmap-json", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    selection = load(selection_path)
    candidates = selection.get("tier2", {}).get("candidates")
    if candidates is None:
        candidates = selection.get("eligible", [])

    candidate = next(
        (item for item in candidates if str(item.get("name")) == args.candidate),
        None,
    )
    if candidate is None:
        raise SystemExit("Candidate not found: " + args.candidate)

    project = args.project.resolve()
    selection_path = resolve_input(project, args.selection_json)
    if selection_path is None:
        raise SystemExit(f"Selection file not found relative to project: {args.selection_json}")
    compare_json = resolve_input(project, args.compare_json)
    scout_json = resolve_input(project, args.scout_json)
    analysis_json = resolve_input(project, args.analysis_json)
    reference_json = resolve_input(project, args.reference_json)
    xmap_json = resolve_input(project, args.xmap_json)
    output = args.output.resolve() if args.output else (
        project / ".decomp-agent" / "challenge" / "candidates" / safe_name(args.candidate)
    )
    output.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "format": "decomp-candidate-pack-v2",
        "candidate": candidate,
        "files": {},
    }

    ledger = project / ".decomp-agent" / "hypotheses.jsonl"
    signature = str(candidate.get("scout", {}).get("signature", "")).strip()
    prior_knowledge = search(
        read_entries(ledger),
        target=str(candidate.get("name", args.candidate)),
        query=signature or "exact match",
        top_k=5,
    )

    source_path = resolve_source(project, candidate)
    if source_path:
        source_dir = output / "source"
        source_dir.mkdir(exist_ok=True)
        shutil.copy2(source_path, source_dir / "source.cpp")
        manifest["source_path"] = str(source_path)
        manifest["files"]["source"] = "source/source.cpp"
        headers = copy_direct_includes(source_path, project, source_dir / "headers")
        if headers:
            manifest["files"]["direct_headers"] = headers
        else:
            (source_dir / "headers").rmdir()
    else:
        manifest["source_error"] = "Could not resolve source implementation."

    evidence_dir = output / "evidence"
    evidence_dir.mkdir(exist_ok=True)

    scout = candidate.get("scout")
    if scout:
        (evidence_dir / "scout.json").write_text(
            json.dumps(scout, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest["files"]["scout"] = "evidence/scout.json"

    if scout_json is not None:
        full_scout = load(scout_json)
        matching = next(
            (item for item in full_scout.get("candidates", []) if item.get("name") == args.candidate),
            None,
        )
        if matching:
            (evidence_dir / "scout-full.json").write_text(
                json.dumps(matching, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest["files"]["scout_full"] = "evidence/scout-full.json"

    for arg_name, filename in (
        ("analysis_json", "analysis.json"),
        ("reference_json", "reference.json"),
        ("xmap_json", "xmap.json"),
    ):
        path = {
            "analysis_json": analysis_json,
            "reference_json": reference_json,
            "xmap_json": xmap_json,
        }[arg_name]
        if path is not None:
            shutil.copy2(path, evidence_dir / filename)
            manifest["files"][arg_name] = "evidence/" + filename

            if arg_name == "analysis_json":
                analysis = load(path)
                function = analysis.get("function", {})
                instructions = analysis.get("instructions", [])
                relationships = analysis.get("relationships", {})
                cfg = analysis.get("cfg", [])
                memory = analysis.get("memory", {})

                (evidence_dir / "assembly.txt").write_text(
                    "\n".join(
                        str(item.get("address", "")) + "  " + str(item.get("text", ""))
                        for item in instructions
                    ) + "\n",
                    encoding="utf-8",
                )
                pcode_lines = []
                for item in instructions:
                    address = str(item.get("address", ""))
                    for op in item.get("pcode", []):
                        inputs = ", ".join(
                            str(value.get("text", "")) for value in op.get("inputs", [])
                        )
                        output = str(op.get("output") or "")
                        if output:
                            pcode_lines.append(
                                address + "  " + output + " = " +
                                str(op.get("op", "")) + "(" + inputs + ")"
                            )
                        else:
                            pcode_lines.append(
                                address + "  " + str(op.get("op", "")) +
                                "(" + inputs + ")"
                            )
                (evidence_dir / "pcode.txt").write_text(
                    "\n".join(pcode_lines) + "\n",
                    encoding="utf-8",
                )
                decompile_c = analysis.get("decompile_c")
                if decompile_c:
                    (evidence_dir / "decompile.c").write_text(
                        str(decompile_c),
                        encoding="utf-8",
                    )
                    manifest["files"]["decompile"] = "evidence/decompile.c"
                (evidence_dir / "cfg.json").write_text(
                    json.dumps(cfg, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                (evidence_dir / "xrefs.json").write_text(
                    json.dumps(
                        [
                            ref
                            for item in instructions
                            for ref in item.get("references", [])
                        ],
                        indent=2,
                        sort_keys=True,
                    ) + "\n",
                    encoding="utf-8",
                )
                (evidence_dir / "relationships.json").write_text(
                    json.dumps(relationships, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                (evidence_dir / "memory.json").write_text(
                    json.dumps(memory, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                (evidence_dir / "function.json").write_text(
                    json.dumps(function, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                manifest["files"]["assembly"] = "evidence/assembly.txt"
                manifest["files"]["pcode"] = "evidence/pcode.txt"
                manifest["files"]["cfg"] = "evidence/cfg.json"
                manifest["files"]["xrefs"] = "evidence/xrefs.json"
                manifest["files"]["relationships"] = "evidence/relationships.json"
                manifest["files"]["memory"] = "evidence/memory.json"
                manifest["files"]["function"] = "evidence/function.json"

    if compare_json is not None:
        shutil.copy2(compare_json, evidence_dir / "compare.json")
        manifest["files"]["compare"] = "evidence/compare.json"
    (output / "prior-knowledge.json").write_text(
        json.dumps(compact(prior_knowledge), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["files"]["prior_knowledge"] = "prior-knowledge.json"

    (output / "candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["files"]["candidate"] = "candidate.json"

    (output / "codex-prompt.md").write_text(
        make_prompt(candidate, prior_knowledge),
        encoding="utf-8",
    )
    manifest["files"]["prompt"] = "codex-prompt.md"

    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
