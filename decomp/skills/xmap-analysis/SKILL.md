---
name: xmap-analysis
description: Analyze linker XMAP files and correlate symbols, sections and addresses with ROM binaries and Ghidra during legacy game reverse engineering.
---

# XMAP Analysis

Use this skill when a project contains a linker map such as `arm9.o.xMAP`.

The XMAP is **build/link evidence**, not semantic proof. Its highest value comes from correlating it with the ROM/binary and Ghidra.

## Workflow

1. Preserve the original XMAP.
2. Inspect its actual format before assuming a vendor/toolchain.
3. Run `decomp/scripts/parse_xmap.py` to create a machine-readable baseline.
4. Identify sections, symbols, addresses and any explicit sizes.
5. Correlate virtual addresses with the actual binary mapping. Never equate a virtual address with a ROM offset without evidence.
6. Compare XMAP symbols with Ghidra's `FUN_*`, `DAT_*` and existing labels.
7. Feed high-confidence names and layout information into function analysis.
8. Keep inferred function sizes and semantic interpretations explicitly marked as inferred.
9. Preserve raw lines that the parser cannot classify.

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

The parser is deliberately conservative. Extend it with a vendor-specific parser only after inspecting a real XMAP sample.
