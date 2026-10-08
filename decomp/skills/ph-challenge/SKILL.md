---
name: ph-challenge
description: Select and solve Phantom Hourglass functions against a decompilation challenge's Tier 1, Tier 2 and optional Tier 3 requirements.
compatibility: OpenCode and Codex
---

# Phantom Hourglass Challenge


## Helper path resolution

Helper paths such as `../../scripts/<helper>` are relative to the directory containing this `SKILL.md`. Resolve them against the skill base directory before passing them to the shell or Ghidra. Do not rely on the target project's current working directory.

## Request routing

Use the challenge pipeline only when the user asks to **select, solve, or verify a challenge tier**.

For a named candidate or a question about an existing candidate pack:
- use targeted inspection/analysis;
- do not regenerate the global report, scout population or reference gate unless the user asks for a fresh selection or the evidence is stale/missing;
- never edit or build merely because a challenge skill is active.

Honor explicit constraints such as "explain first", "do not edit", or "do not compile yet" before advancing phases.

For autonomous selection, use the full objective pipeline and keep complete reports under `.decomp-agent/` while exposing only compact summaries in context.


Use this skill when the goal is the decomp challenge, not merely general PH decompilation.

## 1. Establish a clean baseline

For autonomous challenge work, materialize the permission budget first:

    <python> ../../scripts/session_policy.py init --mode challenge --force

All selectors then receive:

    --policy .decomp-agent/session-policy.json


Run the PH preflight first. Then follow the project's own README/INSTALL and verify a clean build.

Record:
- game version;
- local matched percentage;
- local function count;
- report path and generation command;
- relevant contribution rules.

The local progress numbers must agree with the project's published decomp.dev progress before selecting challenge targets.

## 2. Generate authoritative progress data

Use the project's normal build/compare workflow and generate an objdiff v2 report with the installed `objdiff-cli` when the project supports it.

Do not infer function match status from source comments, filenames, or Ghidra names when an authoritative report is available.

For the selector, preserve the report as:

    .decomp-agent/challenge/report.json

## 3. Generate targeted Tier 2 Ghidra evidence

For Tier 2, do not use the generic top-100 scout: large functions can be penalized by its ranking and omitted.

Run the targeted Ghidra scout against the authoritative report:

    <ghidra> ... -postScript tier2_ghidra_scout.py .decomp-agent/challenge/report.json > .decomp-agent/challenge/tier2-scout.json

It computes the same P75 size gate and analyzes only functions that already satisfy:

    match == 0
    size >= max(256, P75)

The output contains CFG, branch/loop/switch evidence, calls, globals, stores, and signatures.

The scout is evidence only. objdiff remains authoritative.

## 4. Run the unified Tier 2 selector

Run:

    <python> ../../scripts/challenge.py \
      .decomp-agent/challenge/report.json \
      --scout .decomp-agent/challenge/tier2-scout.json \
      --project . \
      --reference .decomp-agent/reference/ph-analysis.json \
      --top 10 \
      -o .decomp-agent/challenge/tier2-selection.json

The unified engine applies the mechanical gates:
- exact zero-match status;
- at least 256 bytes;
- at least the P75 of remaining zero-match functions;
- conditional branch, loop/back-edge or computed-switch evidence;
- rejects accessor-like, thunk, stub/table/initializer candidates;
- reports source-existence status separately;
- ranks eligible candidates with success and game-logic scores.

Then prepare the selected candidate:

    <python> ../../scripts/prepare_candidate.py \
      .decomp-agent/challenge/tier2-selection.json <candidate> \
      --project . \
      --objdiff-cli .\\objdiff-cli.exe \
      --scout-json .decomp-agent/challenge/tier2-scout.json \
      --analysis-json .decomp-agent/targets/<candidate>-analysis.json \
      --reference-json .decomp-agent/reference/ph-analysis.json \
      --xmap-json .decomp-agent/xmap-ghidra.json

The pack contains source, direct headers, objdiff output, Ghidra analysis and supporting evidence when supplied, plus a concise Codex prompt. It also surfaces reusable hypothesis lessons from previous functions when available.

The final "real game logic" classification remains a review step; heuristics are evidence, not proof.

## 5. Tier 1

Prefer a small, clearly undecompiled function that is not an obvious stub/table/data function.

Before editing:
- verify it is genuinely undecompiled in objdiff;
- inspect its Ghidra disassembly/decompiler;
- identify the source file and contribution style;
- preserve the baseline evidence.

Then use `matching-decomp` and require an exact byte match.

## 6. Tier 2

A Tier 2 target must satisfy every gate:

    match_percent == 0
    size >= 256 bytes
    size >= P75(remaining undecompiled sizes)
    confirmed control flow
    not an obvious stub/table/data function

"Confirmed control flow" requires Ghidra scout evidence (`has_branch`, `has_loop`, or `has_switch`).

The engine's game_logic_score is a screening signal, not proof. Manually verify that the function implements real game logic and is not merely an accessor, wrapper, initializer or data helper.

Choose the highest-success candidate among the eligible set rather than blindly choosing the largest one.

## 7. Tier 3

Only attempt Tier 3 after Tier 1 and Tier 2 are solid.

Use the selector's complexity signals plus a written argument covering:
- what makes the function hard;
- unknown types/globals;
- unusual control flow;
- compiler/code-generation traps;
- why it is harder than the Tier 2 target.

A failed but well-documented hard attempt is preferable to pretending an easy function is difficult.

## Failure policy

Stop on infrastructure blockers such as missing required executables, invalid shell invocation, missing project state, or explicit helper infrastructure errors. Do not blindly retry or invent replacement scripts.

Treat source compile errors, linker errors caused by the current hypothesis, and compare mismatches as experiment evidence. Diagnose and iterate one source change at a time.

## Context discipline

Keep authoritative reports and scout JSON on disk. Read only summary fields, the selected candidate, or target-specific evidence needed for the current decision. Never truncate by position ("first three") when relevance filtering can identify the correct records.

## 8. Matching loop

For each chosen function:

    analyze -> hypothesis -> one source change -> dry-run -> build -> compare

Only an exact authoritative match counts as success.

Never call 99% or semantic equivalence a match.

## 9. Deliverable check

Before opening a PR:
- reread `CONTRIBUTING.md` and relevant project docs;
- verify formatting;
- verify the exact function matches;
- ensure only intended changes are included;
- disclose AI assistance when the challenge asks for it and the project's rules allow a contribution.

Keep the selector output and matching evidence available as part of your challenge notes.
