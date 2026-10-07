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


## 12. XMAP-assisted analysis

When a linker map such as `arm9.o.xMAP` is available, parse it before choosing deep reverse-engineering targets:

    python3 /path/to/skills/decomp/scripts/parse_xmap.py arm9.o.xMAP > .decomp-agent/xmap-analysis.json

The parser is intentionally conservative and format-agnostic. Inspect the raw XMAP if the result has a low format confidence or many unclassified lines.

Correlate XMAP symbols with the binary and Ghidra. Do not map virtual addresses directly to ROM offsets without validating the executable's load addresses and layout.

Expose high-confidence XMAP names, sections and addresses to the function-analysis agent. Keep inferred sizes and semantic interpretations marked as inferred.

The dedicated `decomp/skills/xmap-analysis/SKILL.md` contains the evidence policy and correlation workflow.


## 13. XMAP ↔ Ghidra integration

Ghidra projects should be read through Ghidra's supported API. Do **not** parse internal `Zelda.rep/**/*.grf`, `*.gbf` or similar database files directly.

Export program-level evidence from the Ghidra project:

    analyzeHeadless D:\xavi\ghidra_zelda Zelda \
      -process Zelda \
      -scriptPath /path/to/skills/decomp/scripts \
      -postScript export_ghidra_program.py > .decomp-agent/ghidra-program.json

On Windows, use the equivalent path to Ghidra's `analyzeHeadless.bat`.

The export is read-only and contains:

- program/language/compiler metadata;
- image base and address-space information;
- function names and entry/body addresses;
- function signatures/calling conventions;
- symbol table entries;
- memory block boundaries and permissions.

Then correlate it with the parsed XMAP:

    python3 /path/to/skills/decomp/scripts/correlate_xmap.py \
      .decomp-agent/xmap-analysis.json \
      .decomp-agent/ghidra-program.json \
      > .decomp-agent/xmap-ghidra.json

A useful result looks conceptually like:

    XMAP: Player_Update @ 0x02012340
              |
              | exact address
              v
    Ghidra: FUN_02012340 @ 0x02012340
              |
              +-- analyze_function.py
                    -> assembly
                    -> P-code
                    -> CFG
                    -> Xrefs
                    -> callers/callees
                    -> data/memory evidence

The correlator reports unmatched XMAP symbols and unmatched Ghidra functions so the agent can distinguish missing analysis from an actual address mismatch.

Do not pass an address offset unless it has been independently validated from the binary/load layout. A larger match count is not evidence that an offset is correct.


## 14. Reference decompilation projects

A reference project can save a large amount of duplicated reverse-engineering work. For Phantom Hourglass, the main reference is:

    https://github.com/zeldaret/ph

Clone it separately from the target project:

    git clone https://github.com/zeldaret/ph.git

Index its existing source:

    python3 /path/to/skills/decomp/scripts/analyze_reference_project.py \
      /path/to/ph \
      > .decomp-agent/reference/ph-analysis.json

With an XMAP already parsed:

    python3 /path/to/skills/decomp/scripts/analyze_reference_project.py \
      /path/to/ph \
      --xmap .decomp-agent/xmap-analysis.json \
      > .decomp-agent/reference/ph-analysis.json

The analyzer recognizes the `// non-matching` convention used by PH and function names that encode addresses, such as `func_0203c72c` and `func_ov014_02144820`.

Interpret the result as follows:

    unmarked
        -> apparently matching -> skip by default

    known_nonmatching_equivalent
        -> semantic implementation already considered equivalent
        -> reuse it and focus on exact code generation

    known_nonmatching
        -> reuse it as the starting implementation/context
        -> continue matching

For functions with no address encoded in their name, the analyzer can still preserve the source implementation and may correlate by exact name when the XMAP symbol name is available.

### Do not confuse "unmarked" with "proved"

The PH source tree uses explicit `// non-matching` markers. Their absence is useful project evidence, but it is not an exact-match guarantee.

When `objdiff`/build reports from the reference project are available, prefer those results over source comments. Never let the reference project override contradictory target ROM, target XMAP or target Ghidra evidence.
