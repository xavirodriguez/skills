---
name: xmap-analysis
description: Analyze linker XMAP files and correlate symbols, sections and addresses with ROM binaries and Ghidra during legacy game reverse engineering.
---

# XMAP Analysis

Use this skill when a project contains a linker map such as `arm9.o.xMAP`.

The XMAP is **build/link evidence**, not semantic proof. Its highest value comes from correlating it with the ROM/binary and Ghidra.

## Workflow

Before running the Python helpers, complete environment preflight and select the interpreter it reports. On Windows never assume `python3`, and never use Bash shell syntax in PowerShell.

1. Preserve the original XMAP.
2. Inspect its actual format before assuming a vendor/toolchain.
3. Run `decomp/scripts/parse_xmap.py` to create a machine-readable baseline.
4. Export program-level Ghidra evidence with `export_ghidra_program.py`.
5. Correlate XMAP symbols with the exported Ghidra functions/symbols using `correlate_xmap.py`.
6. Identify sections, symbols, addresses and any explicit sizes.
7. Correlate virtual addresses with the actual binary mapping. Never equate a virtual address with a ROM offset without evidence.
8. Compare XMAP symbols with Ghidra's `FUN_*`, `DAT_*` and existing labels.
9. Feed high-confidence names and layout information into function analysis.
10. Pass the correlation JSON to `analyze_function.py` when a function-level evidence snapshot is needed:
    `... -postScript analyze_function.py <function> .decomp-agent/xmap-ghidra.json`
11. Keep inferred function sizes and semantic interpretations explicitly marked as inferred.
12. Preserve raw lines that the parser cannot classify.

## Evidence policy

Classify every conclusion as:

- **HIGH** — explicit in the XMAP or validated against the binary.
- **MEDIUM** — strongly supported by layout/patterns.
- **LOW** — a hypothesis requiring further validation.

Never infer a C type, structure, function responsibility or gameplay meaning from a symbol name alone.

## Useful correlations

Build this chain when the required artifacts exist:

    XMAP symbol
      -> virtual address
      -> binary offset
      -> Ghidra symbol/function/data
      -> assembly/P-code
      -> source hypothesis

If the XMAP and Ghidra disagree, inspect the binary and mapping before renaming anything.

## Output

Keep a structured artifact such as:

    .decomp-agent/xmap/analysis.json

Recommended top-level fields:

- format
- statistics
- sections
- symbols
- correlations
- inferences
- hypotheses
- conflicts

The parser is deliberately conservative. The Ghidra bridge uses `analyzeHeadless` and Ghidra's supported API rather than reading `*.rep/*.grf/*.gbf` internals directly. Extend the XMAP parser with a vendor-specific format only after inspecting a real XMAP sample.


## Ghidra project boundary

Treat the Ghidra project as an opaque database owned by Ghidra. Read it through `analyzeHeadless` and Ghidra scripts, not by parsing `Zelda.rep` internals such as `.grf` or `.gbf` files.
