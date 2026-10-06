# Matching Decompilation Agent — Manual

This guide explains how to use the matching-decomp skill with a real decomp.dev project. The first reference workflow is Dream-Atelier/kl-eod-decomp, but the tooling is intentionally project-agnostic.

## What this version does

The workflow is split into safe, reproducible stages:

1. Inspect the project and discover its real build/compare workflow.
2. Scout likely first targets with Ghidra.
3. Analyze one target into structured assembly/P-code/CFG evidence.
4. Propose the smallest source change using the LLM agent.
5. Dry-run the orchestration before executing commands.
6. Build and compare with the project's authoritative commands.
7. Record raw logs and hypotheses under .decomp-agent/.
8. Repeat one hypothesis at a time.
9. Verify globally after an exact function match.

The Python helpers do not pretend to understand C semantics. They collect evidence and execute explicitly supplied project commands. The LLM agent remains responsible for reasoning about the source change.

## 1. Prepare Klonoa

    git clone --recursive https://github.com/Dream-Atelier/kl-eod-decomp.git
    cd kl-eod-decomp
    # Put your legally obtained ROM at ./baserom.gba
    ./setup.sh
    make
    make compare

Do not skip the initial project build. If it fails, fix the environment before asking the agent to match functions.

## 2. Install the skill

    git clone https://github.com/xavirodriguez/skills.git

Expose decomp/skills/matching-decomp/SKILL.md and decomp/system_prompt.md to your coding agent according to its skill/prompt mechanism.

The scripts live in decomp/scripts/. They are ordinary Python/Ghidra helpers and are not automatically installed into Ghidra.

## 3. Inspect before touching source

From the target project:

    python3 /path/to/skills/decomp/scripts/inspect_project.py .

Save the JSON output:

    mkdir -p .decomp-agent
    python3 /path/to/skills/decomp/scripts/inspect_project.py . > .decomp-agent/project.json

For Klonoa, inspect at least:

- README.md
- Makefile
- config.mk
- objdiff.json
- klonoa-eod-decomp.toml
- scripts/generate_asm.py
- src/
- asm/nonmatchings/
- asm/matchings/

## 4. Understand match status

A function in asm/nonmatchings/ is a useful project-level signal that it still needs work, but it is not proof of exact machine-code status.

Likewise, apparently decompiled C is only complete when the project's authoritative comparison says it matches.

For Klonoa, prefer make compare and make verify-asm over ad-hoc object comparisons.

## 5. Scout with Ghidra

Create/import the ROM in a Ghidra project first. Then run:

    analyzeHeadless <project-dir> <project-name> \
      -process <program> \
      -scriptPath /path/to/skills/decomp/scripts \
      -postScript scout_functions.py

With known status metadata:

    analyzeHeadless <project-dir> <project-name> \
      -process <program> \
      -scriptPath /path/to/skills/decomp/scripts \
      -postScript scout_functions.py /path/to/scout.json

The scout ranks targets using known nonmatching status, instruction count, resolved signature, global/data references, CFG complexity, nearby matching functions, existing structures, problematic control flow/arithmetic, and parameter/callee/caller context.

The score is only a prioritization heuristic.

## 6. Analyze one target

    analyzeHeadless <project-dir> <project-name> \
      -process <program> \
      -scriptPath /path/to/skills/decomp/scripts \
      -postScript analyze_function.py sub_0804B254

Capture the JSON:

    ... -postScript analyze_function.py sub_0804B254 > .decomp-agent/targets/sub_0804B254-analysis.json

Give this evidence to the LLM agent together with the relevant source/TU and the project's build configuration.

## 7. Dry-run before execution

    python3 /path/to/skills/decomp/scripts/run_match.py \
      --project . \
      --target sub_0804B254 \
      --build-command "make -j4" \
      --compare-command "make compare" \
      --iterations 3 \
      --dry-run

Nothing is executed and no source is changed.

## 8. Execute an experiment

After reviewing the proposed source change:

    python3 /path/to/skills/decomp/scripts/run_match.py \
      --project . \
      --target sub_0804B254 \
      --build-command "make -j4" \
      --compare-command "make compare" \
      --iterations 1 \
      --force

The harness records raw build/compare logs under .decomp-agent/targets/<target>/ and a machine-readable ledger at .decomp-agent/hypotheses.jsonl.

Important: this harness executes commands but intentionally does not edit source code. The LLM coding agent should make exactly one source change between iterations.

## 9. Parse comparison output

    python3 /path/to/skills/decomp/scripts/parse_compare.py \
      .decomp-agent/targets/sub_0804B254/iteration-001-compare.log

The parser is conservative and best-effort. Treat its result as extracted evidence, not authoritative semantics.

## 10. Recommended agent loop

    inspect
      ↓
    scout
      ↓
    analyze
      ↓
    propose one change
      ↓
    dry-run
      ↓
    apply one change
      ↓
    build + authoritative compare
      ↓
    parse first mismatch
      ↓
    record hypothesis
      ↓
    repeat

For every iteration record target, hypothesis, evidence, exact source change, match before, match after, first mismatch, and decision.

Never make several unrelated changes before comparing.

## 11. Klonoa completion

When a target reaches an exact match:

    make compare
    make verify-asm

Then inspect neighbouring functions and the final source diff.

Because this project uses legacy GBA compilers and multiple compiler configurations, a function-level match is not the final verification boundary.

## Safety rules

- Start from a clean git worktree.
- Prefer a dedicated branch per target.
- Never overwrite the ROM or generated artifacts unnecessarily.
- Keep raw Ghidra JSON and comparison logs.
- Do not claim an exact match from decompiler similarity.
- Do not guess build commands.
- Do not let the agent rewrite unrelated code.
- Stop when the authoritative compare passes or when the environment is blocked.
