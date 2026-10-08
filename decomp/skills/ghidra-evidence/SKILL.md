---
name: ghidra-evidence
description: Read-only Ghidra/PyGhidra evidence collection for matching decompilation.
compatibility: OpenCode and Codex
---

# Ghidra Evidence

Use this skill to extract evidence from a reverse-engineered program. It does not decide match status and does not edit the Ghidra database.

Prefer the repository's headless helpers when available:

    analyzeHeadless ... -postScript export_ghidra_program.py

For one function:

    analyzeHeadless ... -postScript analyze_function.py <function-or-address>

For challenge candidate discovery, use the project's dedicated scout when available, for example:

    analyzeHeadless ... -postScript tier2_ghidra_scout.py .decomp-agent/challenge/report.json

Collect:
- function bounds and address;
- calling convention and signature;
- assembly and P-code;
- CFG/basic blocks;
- callers/callees and Xrefs;
- strings and referenced data;
- globals and stack accesses;
- control-flow evidence.

Assembly/P-code are evidence. Decompiler C is a hypothesis. The project's authoritative objdiff/build result decides whether the implementation matches.
