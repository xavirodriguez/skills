---
name: matching-decomp
description: Analyze legacy game binaries with Ghidra/PyGhidra and iteratively reconstruct C/C++ until the project's exact build produces a matching object or binary. Use for ARM/Thumb, MIPS, PowerPC, x86 and legacy compilers such as agbcc, IDO, MWCC and old GCC.
---

# Matching Decompilation

The goal is not merely to understand a function. The goal is to reproduce the target machine code under the project's exact compiler, flags, linker and translation-unit conditions.

**Success criterion:** the project's authoritative comparison reports an exact match.

## 0. Environment and shell preflight

Before any helper or build command:
- identify OS and active shell;
- identify a usable Python interpreter;
- identify Ghidra headless, Ninja/Make and objdiff when applicable;
- run `decomp/scripts/preflight.py` when Python is available;
- on Windows without Python, run `decomp/scripts/preflight.ps1` first.

Never assume `python3` on Windows.

Shell commands must match the active shell. In PowerShell never emit Bash-only syntax such as `&&`, `||`, `<<` heredocs, `source`, or `mkdir -p`. Do not use inline Python for project inspection when one of the repository helpers can perform the task. Use separate commands rather than chaining.

If preflight reports a blocker, stop and report the blocker. Do not improvise another shell or language to bypass it.

## 1. Inspect before editing

Identify:

- architecture, endianness and ABI;
- compiler/toolchain and exact flags;
- build system and authoritative compare command;
- target source/translation unit;
- objdiff/decomp.me configuration;
- existing typedefs, structs and macros;
- nearby already-matching functions.

Do not assume ELF, x86_64, Ninja, or a particular compare command.

## 2. Analyze with Ghidra

For repeatable work, use the repository helpers when available:

- `decomp/scripts/analyze_function.py` for a structured JSON evidence snapshot;
- `decomp/scripts/scout_functions.py` to rank practical first targets. Its preferred signals are known `nonmatching` status, small instruction count, resolved signatures, few globals, simple CFG, nearby matching functions, existing structures/types, and absence of known problematic constructs.

Keep the raw JSON artifact for the iteration ledger. It makes later hypotheses reproducible instead of relying on screenshots or transient Ghidra state.

Prefer PyGhidra or headless Ghidra for repeatable analysis.

Collect:

- function address and bounds;
- current signature and calling convention;
- assembly;
- P-code;
- CFG/basic blocks;
- callers/callees;
- Xrefs;
- strings and referenced data;
- imports/exports;
- stack offsets/frame size;
- global/RODATA/BSS references;
- load/store widths and alignment;
- constants and jump tables.

Treat decompiler C as a hypothesis, not ground truth.

## 3. Build an evidence-backed semantic model

Separate **observations** from **inferences**. An observation is directly present in assembly/P-code/metadata; an inference is a proposed explanation. Never feed an inference back into the evidence set as if it were a fact.

Infer:

- return type and parameters;
- local variable types;
- structs and arrays;
- control-flow constructs;
- memory-region ownership;
- call argument mapping.

For non-obvious conclusions keep confidence and evidence, e.g.:

    enemyCount
    confidence: 0.91
    evidence:
      - incremented in loop
      - compared with table length
      - used as array index

Never invent names or types only to make the C look clean.

## 4. Produce the smallest candidate

Use project-native typedefs, structs and macros. Preserve the target translation unit and avoid unrelated cleanup.

Prefer source-level compiler steering over inline assembly.

## 5. Compile and compare

If the project exposes JSON diff output, preserve it as an artifact. Record the first mismatch rather than only the overall percentage. When no machine-readable diff exists, capture the smallest useful textual diff and the exact command used.

Use the fastest authoritative local comparison available.

Typical commands may look like:

    ninja
    objdiff diff --json --function <function>

or:

    make compare

Parse the result for:

- match percentage;
- first mismatching instruction;
- changed registers;
- changed immediates;
- changed stack offsets;
- changed branches;
- changed calls.

A high partial match is not success.

## 6. Diagnose before changing code

Classify the mismatch first:

| Symptom | First hypothesis |
|---|---|
| stack size/offset | local type, alignment, lifetime, scope |
| same operations/different registers | declaration/evaluation order, live ranges |
| branch layout differs | condition polarity, loop form, early return |
| load/store width differs | signedness/type width |
| address materialization differs | symbol vs constant, array shape |
| call arguments differ | signature/ABI/evaluation order |
| extra/missing instruction | expression shape/compiler idiom |
| neighbour regressed | translation-unit/compiler coupling |

Then change one thing and re-run the diff.

## 7. Keep a hypothesis ledger

Use a compact machine-readable record when possible:

    iteration, target, hypothesis, evidence, source_change,
    match_before, match_after, first_mismatch, decision

A rejected hypothesis is valuable state. Record it explicitly so an agent does not cycle back to the same explanation.

Record every meaningful experiment:

    iteration
    hypothesis
    source change
    match before
    match after
    instruction delta
    decision

Do not repeat failed hypotheses.

Do not impose an arbitrary 15-iteration limit when builds are cheap. Continue while experiments provide evidence, subject to the user's budget and a runaway-loop guard.

## 8. Validate globally

A scout score is only a prioritization heuristic. It does **not** establish that a function is unmatched, easy, or semantically understood. Confirm all of those with the project's source and comparison data.

After an exact function match:

1. Run the project's full object/ROM comparison.
2. Check neighbouring functions for regressions.
3. Remove temporary barriers, register pins and debugging code.
4. Review the final source diff.

This is especially important for GBA/agbcc: code generation can couple functions in the same translation unit.

## 9. Architecture-specific guidance

### GBA / agbcc

Pay special attention to:

- symbol references vs integer address constants;
- multidimensional array shape;
- bitfield container width;
- global reloads vs cached values;
- temporary width;
- local lifetime and stack layout;
- operand order;
- linker-script symbols;
- full-ROM coupling.

### MIPS / IDO

Pay special attention to:

- delay slots;
- o32 argument rules;
- branch polarity/layout;
- declaration order;
- sign extension;
- HI/LO operations;
- struct offsets.

### PowerPC / MWCC

Pay special attention to:

- stack alignment;
- register save/restore;
- TOC/global addressing;
- scheduling;
- aggregate passing;
- compiler-specific struct layout.

## 10. Failure handling

When C and assembly disagree:

1. Trust the instruction stream.
2. Inspect P-code for the disputed operation.
3. Check ABI and callers/callees.
4. Test the smallest source-level hypothesis.
5. Recompile and compare.

If the environment cannot build or compare, report the exact blocker. Never claim a match from semantic similarity alone.

## Output

For analysis, report:

1. target and architecture;
2. ABI/compiler/build facts;
3. signature hypothesis;
4. semantic findings;
5. evidence/confidence;
6. candidate C;
7. comparison result;
8. next hypothesis if unmatched.

For completion, report exact-match status and the verification command.


## 11. Use the agent harness

For a real project, use the helpers as a pipeline rather than invoking them as isolated scripts:

1. Run decomp/scripts/inspect_project.py and save its JSON as the project baseline.
2. Identify the authoritative build and compare commands from the project itself.
3. Scout candidates with Ghidra.
4. Run decomp/scripts/analyze_function.py for one target and save its JSON evidence.
5. Ask the coding agent to propose exactly one source change.
6. Run decomp/scripts/run_match.py --dry-run to verify the commands before execution.
7. Apply the single source change.
8. Run decomp/scripts/run_match.py --force for one build/compare experiment.
9. Parse the raw compare log with decomp/scripts/parse_compare.py.
10. Record the hypothesis, evidence, source change, result and first mismatch.
11. Repeat until exact match or a concrete blocker.

The harness deliberately does not edit source or invent commands. The LLM is the reasoning layer; the scripts are the evidence, execution and audit layer.

## 12. Safety and reproducibility

Before autonomous experiments:

- require a clean git worktree or a dedicated target branch;
- preserve raw Ghidra JSON;
- preserve raw build/compare logs;
- make one source change per iteration;
- never treat a heuristic scout score as proof;
- never treat a parser result as authoritative when the project provides a stronger compare result;
- for GBA/agbcc, run the project's full verification after a function-level match.
