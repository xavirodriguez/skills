---
name: ph-decomp
description: Orchestrate Zelda: Phantom Hourglass decompilation workflows with task-aware routing, PH-specific evidence gates and authoritative matching verification.
compatibility: OpenCode and Codex
---

# Phantom Hourglass Decompilation

## Helper path resolution

Helper paths such as \`../../scripts/<helper>\` are relative to the directory containing this \`SKILL.md\`. Resolve them against the skill base directory before passing them to the shell or Ghidra. Do not rely on the target project's current working directory.

## Role

This is the **Phantom Hourglass entry-point**. Generic reverse-engineering, matching and experiment rules live in \`matching-decomp\`. Challenge selection/verification rules live in \`ph-challenge\`.

Do not duplicate those policies here. Load the secondary skill only when the workflow reaches that phase.

## Task routing

Choose the smallest PH workflow that satisfies the request:

- **EXPLAIN** — answer a conceptual question about PH, assembly, structs, vtables or compiler behavior. Read only what is needed.
- **INSPECT** — inspect a named PH source file, symbol, report or project area. Do not start the global pipeline.
- **ANALYZE** — collect targeted Ghidra/XMAP/reference evidence for a known target.
- **TARGET_MATCH** — match a concrete function supplied by the user. Skip candidate selection and global scouting. Load \`matching-decomp\` for the matching loop.
- **SELECT** — choose an unknown target. Run the PH reference/XMAP/candidate gates.
- **CHALLENGE** — select, solve or verify a Tier 1/2/3 challenge target. Load \`ph-challenge\`.

Explicit user constraints remain active. Do not edit, build, compare, switch branches or create worktrees unless the request authorizes the action.

## Session policy

For workflows that execute helpers, a policy file can turn the request constraints into executable gates:

    <python> ../../scripts/session_policy.py init --mode target-match --force
    <python> ../../scripts/session_policy.py show

Supported modes:

    explain
    inspect
    analyze
    target-match
    select
    challenge

Pass \`--policy .decomp-agent/session-policy.json\` to helpers that support it. Missing policy means no additional restriction; an existing policy is enforced.

## PH-specific baseline

Before **TARGET_MATCH**, **SELECT** or **CHALLENGE** work:

1. Establish the game version (EUR/USA) and active build configuration.
2. Run the PH preflight when the selected workflow requires it.
3. Identify \`tools/configure.py\`, Ninja targets, \`objdiff.json\`, build outputs and the authoritative compare/report command.
4. Treat \`arm9.o.xMAP\` as linker/build evidence. Never assume a virtual address is a ROM/file offset.

Use the reference project only as prior work:

    https://github.com/zeldaret/ph

Its source annotations are not match proof. Prefer its verified build/report data when available.

## Targeted evidence

For a supplied function/address, use only the evidence needed to resolve that target:

    <python> ../../scripts/inspect_project.py <target>
    <python> ../../scripts/analyze_function.py <function-or-address>

Parse XMAP only when it materially helps:

    <python> ../../scripts/parse_xmap.py <xmap> -o <target>/.decomp-agent/xmap-analysis.json

When Ghidra project-level identity is needed:

    analyzeHeadless ... -postScript export_ghidra_program.py

Never invent an address delta.

## Selection gates

For **SELECT**:

1. inspect the target project;
2. analyze the PH reference project;
3. parse/correlate XMAP where available;
4. generate the authoritative objdiff report;
5. run the function-level candidate gate;
6. choose one target.

An incomplete objdiff unit does not mean every function in the unit is unmatched.

For **CHALLENGE**, follow \`ph-challenge\` and its unified selector. Heuristics are screening evidence; objdiff remains authoritative.

## Matching handoff

Once a concrete target is selected, load:

    matching-decomp

Then follow its evidence -> hypothesis -> one source change -> build -> authoritative compare -> ledger loop.

A partial match is not success. An exact authoritative target match is required before completion.

## Failure handling

Stop on infrastructure blockers such as missing executables/paths, invalid shell invocation, unavailable project state or helper infrastructure errors.

Treat compiler/linker failures caused by the current source hypothesis and compare mismatches as experiment evidence. Do not blindly retry infrastructure failures or replace helpers with ad-hoc scripts.

## Output

For PH orchestration, report:

1. game version and target;
2. relevant build/compiler facts;
3. evidence source and confidence;
4. target-selection rationale when applicable;
5. authoritative compare result;
6. session-policy/blocker status;
7. paths to preserved artifacts under \`.decomp-agent/\`.
