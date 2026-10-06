---
name: matching-decomp
description: Decompile binaries with Ghidra or PyGhidra and iteratively match the generated C against the original assembly until objdiff reports 100 percent. Use for matching decompilation, reverse engineering of MIPS PowerPC ARM or x86 binaries, legacy compilers (IDO, MWCC, GCC 2.x/3.x), ninja + objdiff workflows, function matching, and byte-accurate C reconstruction from ELF or object files.
---

# Matching Decompilation

Produce C source that compiles to the **exact same instructions** as a target function in a binary. Matching is measured by `objdiff` (or equivalent). Byte-accurate match is the only success criterion.

## Prerequisites

The environment must provide:
- **PyGhidra** (`pip install pyghidra`) or Ghidra `analyzeHeadless`
- A matching project with `ninja` build and `objdiff`
- Project headers defining types such as `s32`, `u16`, `f32`, `u8*`, etc.

If tools are missing, tell the user what to install before proceeding.

## Workflow

### 1. Extract decompiled C

Run the extraction script (preferred):

```bash
python scripts/extract_decomp.py <binary_path> <function_name>
```

It prints JSON with `function`, `address`, and `c_code`.

If only headless Ghidra is available, fall back to `analyzeHeadless` and parse the decompiler output manually.

Optional semantic cleanup on `main` only:

```bash
python scripts/pcode_rename.py <binary_path>
```

### 2. Normalize syntax

Transform Ghidra pseudocode into compiler-friendly C:

- Map Ghidra types to project types (`int` to `s32`, `undefined4` to `u32`, pointers to `u8*` or struct pointers).
- Restore correct parameter names and return type from the function signature or project headers.
- Remove Ghidra artefacts (`CONCAT`, `ZEXT`, temporary names like `uVar1`).
- Prefer the coding style of the existing `src/` tree.

Write the candidate into the correct source file under `src/`.

### 3. Compile-and-match loop (max 15 iterations)

Each iteration:

```bash
ninja && objdiff diff --json --function <function_name>
```

Interpret the result:

| Result | Action |
|--------|--------|
| Compilation error | Fix types, missing includes, struct members, macros. Re-run. |
| Match = 100.0% | **SUCCESS.** Stop. Commit with message `decomp: Match <function_name>`. |
| Match < 100% | Read the instruction diff. Apply heuristics from [references/compiler-heuristics.md](references/compiler-heuristics.md). Edit C and re-evaluate. |

Never stop on partial matches (85%, 95%, ...). Continue until 100% or the iteration limit.

### 4. When stuck

If after ~10 iterations the same few instructions keep mismatching:

1. Dump the current assembly side-by-side (`objdiff` output).
2. Consult [references/compiler-heuristics.md](references/compiler-heuristics.md) for the specific symptom.
3. Try a more aggressive rewrite (reorder locals, change loop shape, add/remove blocks `{}` to alter stack frame).
4. If still blocked, report the remaining mismatch and ask the user for domain knowledge (struct layouts, known macros, compiler flags).

## Constraints

- Matching accuracy overrides clean or modern C style.
- Prefer the project's existing idioms and macros over inventing new ones.
- Do not invent symbols or globals that do not exist in the binary or headers.
- Keep changes minimal and focused on the target function.

## Scripts

| Script | Purpose |
|--------|---------|
| [scripts/extract_decomp.py](scripts/extract_decomp.py) | Headless decompile of any named function to JSON |
| [scripts/pcode_rename.py](scripts/pcode_rename.py) | Optional P-code heuristics to rename locals in `main` |

## References

- [references/compiler-heuristics.md](references/compiler-heuristics.md) — register swaps, control-flow, stack, immediates
- [references/setup.md](references/setup.md) — tool installation and minimal matching project layout
