# Ghidra matching helpers

## Context-friendly output

Large analysis/selection artifacts should be written with `-o` into `.decomp-agent/`. `candidate_gate.py` and `challenge.py` keep the full JSON on disk and print a compact summary when `-o` is supplied. Use `--full-output` only when the complete JSON is explicitly needed on stdout.


These scripts are intentionally read-only: they turn Ghidra's analysis into structured evidence for a matching-decomp workflow.

## `analyze_function.py`

Run from Ghidra headless mode after importing/opening the target program:

```text
analyzeHeadless <project-dir> <project-name> -process <program> \
  -scriptPath decomp/scripts -postScript analyze_function.py <function-or-address>
```

The script emits one JSON document to stdout containing the function signature, assembly, P-code, CFG edges, callers/callees, Xrefs, strings, stack accesses, and referenced data.

## `scout_functions.py`

Run the same way without a target argument. It ranks functions that are good candidates for a first matching contribution. The score deliberately favours small, self-contained functions with useful symbols/types and nearby matching context rather than merely selecting the shortest function.

Both scripts are evidence collectors. They do not edit source code or claim a match.

## Function scouting signals

`scout_functions.py` combines these signals:

- known `nonmatching` status when supplied by project metadata or a local Ghidra annotation;
- low instruction count;
- resolved function signature;
- few references to global/data objects;
- simple CFG;
- neighbouring functions known to match;
- parameters/locals using already-defined structures;
- absence of constructs that often make matching harder, such as computed control flow or unusual arithmetic;
- manageable parameter/callee counts and useful caller context.

For authoritative project status, pass a small JSON metadata file as the first script argument:

```json
{
  "nonmatching": ["0x08000100", "function_name"],
  "matching": ["0x08000200"],
  "matching_ranges": [["0x08001000", "0x08001080"]]
}
```

This keeps the scout useful across different decompilation projects without hard-coding one project's symbol conventions.


## inspect_project.py

Read-only project discovery helper:

    python3 inspect_project.py /path/to/project

It reports build/config files, matching/nonmatching directories, source-file counts and useful build/decompilation signals. It does not infer the authoritative commands; the agent must inspect the project configuration.

## parse_compare.py

Best-effort parser for captured compare output:

    python3 parse_compare.py .decomp-agent/targets/<target>/iteration-001-compare.log

It extracts explicit match percentages, first-mismatch addresses and failure/match evidence. It is not a replacement for objdiff or the project's own compare command.

## run_match.py

Safe experiment harness:

    python3 run_match.py --project . --target sub_0804B254 \
      --build-command "make -j4" \
      --compare-command "make compare" \
      --iterations 1 --dry-run

Dry-run executes nothing. To execute the explicitly supplied commands:

    python3 run_match.py --project . --target sub_0804B254 \
      --build-command "make -j4" \
      --compare-command "make compare" \
      --iterations 1 --force

The harness records state under .decomp-agent/, including raw logs and a structured hypothesis ledger. It intentionally does not modify source code.

When a build command ends non-zero because of a final ROM/hash check but the function object is still available, use:

    python3 run_match.py --project . --target <function>       --build-command "ninja"       --compare-command "<authoritative compare>"       --compare-on-build-failure       --allow-build-failure-if-compare-passes       --force


## Recommended end-to-end workflow

For a first target:

    inspect_project.py .
    scout_functions.py
    analyze_function.py <target>
    run_match.py --dry-run
    [LLM proposes/applies one source change]
    run_match.py --force
    parse_compare.py <raw-log>

See decomp/MANUAL.md for the complete Klonoa workflow and safety rules.


## Tier 2 challenge automation

For Phantom Hourglass Tier 2, use the targeted Ghidra scout and the unified challenge engine instead of the generic top-100 scout:

    analyzeHeadless <project-dir> <project-name> -process <program> \
      -scriptPath decomp/scripts \
      -postScript tier2_ghidra_scout.py .decomp-agent/challenge/report.json \
      > .decomp-agent/challenge/tier2-scout.json

Then:

    python decomp/scripts/challenge_autopilot.py \
      .decomp-agent/challenge/report.json \
      --scout .decomp-agent/challenge/tier2-scout.json \
      --project . \
      --objdiff-json objdiff.json \
      --objdiff-cli .\\objdiff-cli.exe \
      --write-packs

The autopilot computes the project's remaining undecompiled P75, enforces the 256-byte floor and control-flow gates, rejects common accessor/stub/table/initializer shapes, and writes Codex-ready candidate packs. It does not modify source code and does not claim that heuristics prove game logic.


## OpenCode path resolution

The skills under `decomp/skills/*/SKILL.md` reference shared helpers using paths relative to their own skill directory:

    ../../scripts/<helper>

This is intentional. OpenCode resolves paths in a skill relative to the directory containing `SKILL.md`, and an explicit skill source can contain nested `SKILL.md` files. Keeping the helpers under `decomp/scripts/` preserves the same repository layout for Codex and OpenCode.

Run `python validate_skill_layout.py` from this directory to verify skill names, frontmatter and referenced helper paths.
