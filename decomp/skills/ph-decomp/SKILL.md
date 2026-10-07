---
name: ph-decomp
description: Orchestrate Phantom Hourglass matching decompilation on Windows or POSIX. Mandatory preflight, reference-project gate, XMAP correlation, Ghidra evidence and authoritative objdiff verification.
---

# Phantom Hourglass Decompilation

Use this skill as the entry point for Zelda: Phantom Hourglass. It orchestrates reference-decomp, xmap-analysis and matching-decomp.

Do not start by selecting an incomplete objdiff unit. Establish the environment and run the reference/XMAP gates first.

## 1. Preflight first

Use the native Windows check when Python may be unavailable:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File <skills>/decomp/scripts/preflight.ps1 <target>

Once Python is available:

    <python> <skills>/decomp/scripts/preflight.py <target> --reference <ph-reference> --xmap <xmap>

On POSIX:

    <python> <skills>/decomp/scripts/preflight.py <target> --reference <ph-reference> --xmap <xmap>

Do not assume \`python3\` on Windows. Use the interpreter reported by preflight.

Shell commands must match the active shell. In PowerShell do not use Bash chaining, Bash heredocs, \`source\`, \`mkdir -p\`, or other Bash-only syntax. Do not write inline Python for repository inspection when a helper script exists. Run commands as separate steps.

If preflight reports a blocker, stop and report it. Do not improvise shell syntax or bypass the blocker.

## 2. Inspect the target

Run:

    <python> <skills>/decomp/scripts/inspect_project.py <target> > <target>/.decomp-agent/project.json

If an ARM9 XMAP exists, parse it now, before the reference gate:

    <python> <skills>/decomp/scripts/parse_xmap.py <xmap> -o <target>/.decomp-agent/xmap-analysis.json

For PH, identify:
- EUR or USA version;
- compiler and flags;
- \`tools/configure.py\`;
- Ninja targets;
- \`objdiff.json\`;
- \`build/<version>/arm9.o.xMAP\`;
- authoritative report/check commands.

Never invent build or compare commands.

## 3. Reference gate — mandatory

Locate the local clone of:

    https://github.com/zeldaret/ph

Run:

    <python> <skills>/decomp/scripts/analyze_reference_project.py <ph-reference> --xmap <target>/.decomp-agent/xmap-analysis.json --objdiff <ph-reference>/objdiff.json -o <target>/.decomp-agent/reference/ph-analysis.json

If <ph-reference>/objdiff.json does not exist, omit the --objdiff argument.

Then:

    <python> <skills>/decomp/scripts/candidate_gate.py <target>/objdiff.json <target>/.decomp-agent/reference/ph-analysis.json -o <target>/.decomp-agent/reference/candidate-gate.json

The candidate gate is a hard selection filter:
- \`skip_unit_by_default\`: do not re-decompile functions covered by unmarked reference source unless target evidence proves a mismatch.
- \`inspect_reference_nonmatching\`: reuse the reference implementation/context and focus on exact code generation.
- \`inspect_reference\`: inspect reference evidence manually before choosing a target.
- \`target_analysis_allowed\`: no reference function was correlated to the unit.

Do not equate an incomplete objdiff unit with every function in that unit being unmatched.

## 4. XMAP/Ghidra correlation

The XMAP was parsed in step 2. If a Ghidra project is available, use Ghidra's supported headless API:

    analyzeHeadless.bat <project-dir> <project-name> -process <program> -scriptPath <skills>/decomp/scripts -postScript export_ghidra_program.py

Then:

    <python> <skills>/decomp/scripts/correlate_xmap.py <target>/.decomp-agent/xmap-analysis.json <target>/.decomp-agent/ghidra-program.json -o <target>/.decomp-agent/xmap-ghidra.json

Use exact addresses where possible. Never invent an address delta.

## 5. Select one function

Choose one target only after the gates.

A valid target must:
- be actually incomplete in authoritative target comparison;
- not be blocked by an unmarked reference implementation by default;
- have a concrete source file/TU;
- have a resolved XMAP/Ghidra identity when available.

If the only evidence is "objdiff unit incomplete", perform more inspection instead of assuming the function is unmatched.

## 6. Matching loop

Use matching-decomp:
1. analyze one function;
2. preserve JSON evidence;
3. propose exactly one source change;
4. dry-run the harness;
5. build and compare;
6. parse the first mismatch;
7. record one hypothesis and result;
8. repeat.

Never call semantic equivalence an exact match.

## 7. Windows execution

Use separate commands, for example:

    Set-Location D:\xavi\ph
    <python> <skills>\decomp\scripts\inspect_project.py .

For the harness:

    <python> <skills>\decomp\scripts\run_match.py --project . --target <function> --shell powershell --build-command "ninja arm9" --compare-command "ninja report check" --dry-run

Do not generate \`&&\`, \`||\`, Bash heredocs, or \`python3 -c\` inspection snippets in PowerShell.

## 8. Stop conditions

Stop only for:
- verified exact target match;
- concrete environment blocker;
- explicit user budget.

Preserve diagnostic artifacts when blocked.
