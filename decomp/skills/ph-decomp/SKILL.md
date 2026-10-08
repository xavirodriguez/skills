---
name: ph-decomp
description: Orchestrate Phantom Hourglass matching decompilation on Windows or POSIX with task-aware routing, targeted analysis and authoritative verification.
compatibility: OpenCode and Codex
---

# Phantom Hourglass Decompilation

## Task routing

Choose the smallest workflow that satisfies the request before starting the pipeline.

- **EXPLAIN / INSPECT:** read the requested file/symbol and answer. Do not run preflight, reference, XMAP or candidate gates.
- **ANALYZE:** for a known function/address, run only the checks required for Ghidra/analysis. Do not run global selection gates.
- **TARGET_MATCH:** when the user names the function, skip candidate selection, reference gate and XMAP gate unless one is required to resolve the target. Verify the real build/compare command before matching.
- **SELECT / CHALLENGE:** use the full preflight -> inspection -> reference/XMAP -> candidate pipeline.

Never let activation of `ph-decomp` override explicit user constraints. Track READ/ANALYZE/EDIT/BUILD/COMPARE/SELECT permissions for the session.

Do not create worktrees, reset files, switch branches, or discard user changes unless the workflow explicitly calls for isolation and the user has authorized that mutation.


Use this skill as the entry point for Zelda: Phantom Hourglass. It orchestrates reference-decomp, xmap-analysis and matching-decomp.

Do not start by selecting an incomplete objdiff unit. Establish the environment and run the reference/XMAP gates first.

## 1. Preflight when the selected mode requires it

For **SELECT**, **CHALLENGE**, and **TARGET_MATCH**, establish the minimum required environment before helpers or build/compare commands.

For **EXPLAIN**, **INSPECT**, and targeted read-only analysis, do not run the full PH preflight unless the requested analysis actually needs it.

Use the native Windows check when Python may be unavailable:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ../../scripts/preflight.ps1 <target>

Once Python is available:

    <python> ../../scripts/preflight.py <target> --reference <ph-reference> --xmap <xmap>

On POSIX:

    <python> ../../scripts/preflight.py <target> --reference <ph-reference> --xmap <xmap>

Do not assume `python3` on Windows. Use the interpreter reported by preflight.

Shell commands must match the active shell. In PowerShell do not use Bash chaining, Bash heredocs, `source`, `mkdir -p`, or other Bash-only syntax. Do not write inline Python for repository inspection when a helper script exists. Run commands as separate steps.

If preflight reports a blocker, stop and report it. Do not improvise shell syntax or bypass the blocker.

## 2. Inspect the target

Run:

    <python> ../../scripts/inspect_project.py <target> > <target>/.decomp-agent/project.json

If an ARM9 XMAP exists, parse it now, before the reference gate:

    <python> ../../scripts/parse_xmap.py <xmap> -o <target>/.decomp-agent/xmap-analysis.json

For PH, identify:
- EUR or USA version;
- compiler and flags;
- `tools/configure.py`;
- Ninja targets;
- `objdiff.json`;
- `build/<version>/arm9.o.xMAP`;
- authoritative report/check commands.

Never invent build or compare commands.

## 3. Reference gate — mandatory for SELECT/CHALLENGE

For **TARGET_MATCH** with a concrete user-supplied function, skip this gate unless reference evidence is required to resolve or interpret the target.

Locate the local clone of:

    https://github.com/zeldaret/ph

Run:

    <python> ../../scripts/analyze_reference_project.py <ph-reference> --xmap <target>/.decomp-agent/xmap-analysis.json --objdiff <ph-reference>/objdiff.json -o <target>/.decomp-agent/reference/ph-analysis.json

If <ph-reference>/objdiff.json does not exist, omit the --objdiff argument.

Then:

    <python> ../../scripts/candidate_gate.py <target>/objdiff.json <target>/.decomp-agent/reference/ph-analysis.json -o <target>/.decomp-agent/reference/candidate-gate.json

The candidate gate is a hard selection filter:
- `skip_unit_by_default`: do not re-decompile functions covered by unmarked reference source unless target evidence proves a mismatch.
- `inspect_reference_nonmatching`: reuse the reference implementation/context and focus on exact code generation.
- `inspect_reference`: inspect reference evidence manually before choosing a target.
- `target_analysis_allowed`: no reference function was correlated to the unit.

Do not equate an incomplete objdiff unit with every function in that unit being unmatched.

## 4. XMAP/Ghidra correlation

For **SELECT/CHALLENGE**, run the full correlation gate. For **TARGET_MATCH** or **ANALYZE**, use XMAP only when it materially helps resolve the supplied target.

The XMAP was parsed in step 2. If a Ghidra project is available, use Ghidra's supported headless API:

    analyzeHeadless.bat <project-dir> <project-name> -process <program> -scriptPath <skills>/decomp/scripts -postScript export_ghidra_program.py

Then:

    <python> ../../scripts/correlate_xmap.py <target>/.decomp-agent/xmap-analysis.json <target>/.decomp-agent/ghidra-program.json -o <target>/.decomp-agent/xmap-ghidra.json

Use exact addresses where possible. Never invent an address delta.

## 5. Select one function

For challenge work, delegate objective selection to ph-challenge and its unified challenge.py engine. For normal decompilation, select a concrete function only after the reference/XMAP evidence gates.


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

Do not generate `&&`, `||`, Bash heredocs, or `python3 -c` inspection snippets in PowerShell.

## Failure classification

Stop on genuine environment blockers: missing required executables/paths, invalid shell invocation, unavailable project state, or infrastructure errors such as `helper_unknown_error`.

Do not blindly retry failed infrastructure commands, switch shell syntax, or create ad-hoc inline scripts to replace a helper.

Treat compiler errors, linker errors caused by the current source hypothesis, partial matches, and compare mismatches as experiment evidence. Diagnose them and continue one hypothesis at a time within the user's action budget.

## Context discipline

Write large JSON results to `.decomp-agent/` and keep stdout concise. Read only the records relevant to the active target or current gate. Do not discard data by taking the first three or first ten results; filter by target identity instead.

Load `ph-challenge`, `matching-decomp`, `reference-decomp`, or `xmap-analysis` instructions only when the selected workflow reaches that phase.

## 8. Stop conditions

Stop only for:
- verified exact target match;
- concrete environment blocker;
- explicit user budget.

Preserve diagnostic artifacts when blocked.
