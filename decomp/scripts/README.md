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


## Session policy

Create a workflow policy before autonomous execution:

    python3 session_policy.py init --mode target-match --force

The main modes are `explain`, `inspect`, `analyze`, `target-match`, `select` and `challenge`.

Helpers that can perform gated actions accept:

    --policy .decomp-agent/session-policy.json --require-policy

A missing policy preserves backward compatibility. An existing policy is enforced.

## Hypothesis knowledge

The project-level ledger lives at `.decomp-agent/hypotheses.jsonl`. Search related experiments with:

    python3 hypothesis_knowledge.py .decomp-agent/hypotheses.jsonl --target <function> --query "<symptom or hypothesis>"

The search ranks prior entries by textual overlap, mismatch families and successful match improvements. It is deliberately compact so previous work can be reused without loading the entire ledger into context.


## OpenCode bundling

Use `package_opencode.py` to produce a self-contained OpenCode source:

    python3 package_opencode.py --output /path/to/opencode-decomp-skills --force

It copies only directories containing `SKILL.md`, places shared helpers under `_runtime/`, and rewrites `../../scripts/` references to `../_runtime/`. The canonical source remains `decomp/skills/` + `decomp/scripts/`.


## Autonomous challenge batch matching

challenge_batch.py is the persistent controller for multi-target autonomous matching. It keeps queue/state in:

    .decomp-agent/challenge/session.json

Typical Tier 2 bootstrap:

    python decomp/scripts/challenge_batch.py init --project . --report .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --reference .decomp-agent/reference/ph-analysis.json --tier tier2 --quota 0 --max-stagnation 3 --policy .decomp-agent/session-policy.json --require-policy

Then:

    python decomp/scripts/challenge_batch.py next --session .decomp-agent/challenge/session.json --claim

After one authoritative match experiment:

    python decomp/scripts/challenge_batch.py record --session .decomp-agent/challenge/session.json --target <function> --before <before> --after <after>

For an exact match, record --exact requires an authoritative report refresh command and refreshes/rescores the queue automatically. This makes report refresh part of the success transition rather than an optional memory step.

max-stagnation is a no-progress threshold, not an arbitrary total-iteration limit. Positive match deltas reset it. A candidate that reaches the threshold is marked blocked and will not be selected again.

The controller never edits source code. The LLM remains responsible for the source hypothesis; the controller owns candidate state, ranking, refresh and transitions.

## Ghidra launcher detection

Use:

    python decomp/scripts/ghidra_launcher.py detect --ghidra-home <Ghidra>

to locate pyghidraRun and analyzeHeadless. Use:

    python decomp/scripts/ghidra_launcher.py script-runtime --script <collector.py>

to decide which launcher the collector expects. Ghidra documents pyghidraRun.bat as the Windows PyGhidra launch path and -H as headless mode.

The current repository collectors use Ghidra's native headless scripting API, so they should continue to run under analyzeHeadless unless explicitly migrated to PyGhidra.


## Execution guardrails

### source_edit.py

Use the deterministic UTF-8 editor for autonomous source changes. It supports complete-file replacement, exact-text replacement and line-range replacement. Existing files can be protected with an expected SHA-256, and writes are atomic.

Example:

    python source_edit.py replace-text --project . --path src/foo.cpp --old-file .decomp-agent/old.txt --new-file .decomp-agent/new.txt --expected-sha256 <sha256>

The helper never invokes a shell patcher. Do not call `apply_patch` from PowerShell/cmd as an alternative.

### compare_target.py

Use this helper to obtain an agent-friendly per-function objdiff result. It calls `objdiff-cli report generate -f json` with stdin disabled and extracts the requested function by name or `name|address`.

Example:

    python compare_target.py --project . --target FS_LoadOverlay --objdiff-cli .\\objdiff-cli.exe

It reports `match_percent`, `exact_match`, size, address and unit as JSON. It does not open the interactive objdiff UI.

### run_match.py transport policy

Autonomous build/compare experiments must run through `run_match.py`. The harness rejects nested `codex`/ `opencode` invocations and classifies known edit/TTY transport failures as `tool-transport-failure`. This state is telemetry only; it is not candidate stagnation.

## Integration evidence helper

Validate an evidence document before recording an object/link integration result:

    python integration_check.py .decomp-agent/integration/<target>.json

The validator requires explicit `function`, `object`, `range`, and `evidence` data for each region and computes the function end from its entry/size. It rejects function ranges that fall outside the declared object/integration range and rejects multi-region evidence that is marked as merely mirrored.

## Function integration state

The autonomous challenge controller treats an exact function match as `integration-pending` until object/link integration is verified.

Use:

    python challenge_batch.py integration-record \
      --session .decomp-agent/challenge/session.json \
      --target <function> \
      --status pass \
      --evidence .decomp-agent/integration/<target>.json

The evidence JSON separates `function`, `object`, `range`, `padding` and regional evidence. A multi-region change needs independent evidence for every region.

Candidate and compare outputs now expose explicit `function_entry`, `function_size` and `translation_unit` fields. Legacy `address`/`size` aliases are retained for compatibility.
