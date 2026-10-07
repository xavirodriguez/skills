---
name: ph-challenge
description: Select and solve Phantom Hourglass functions against a decompilation challenge's Tier 1, Tier 2 and optional Tier 3 requirements.
---

# Phantom Hourglass Challenge

Use this skill when the goal is the decomp challenge, not merely general PH decompilation.

## 1. Establish a clean baseline

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

## 3. Generate Ghidra evidence

Export the Ghidra program if available, then run the scout with the challenge control-flow evidence:

    <ghidra> ... -postScript scout_functions.py

Save the output as:

    .decomp-agent/challenge/scout.json

The scout is evidence only. It does not decide whether a function is matched.

## 4. Run the selector

Run:

    <python> <skills>/decomp/scripts/challenge_selector.py \
      .decomp-agent/challenge/report.json \
      --scout .decomp-agent/challenge/scout.json \
      --top 20 \
      -o .decomp-agent/challenge/selection.json

The selector produces:
- Tier 1 candidates;
- Tier 2 candidates that satisfy the size and control-flow gates;
- Tier 3 candidates ranked by objective complexity signals;
- the exact P75 used for Tier 2;
- the number of remaining undecompiled functions.

The target report is authoritative for match status.

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

The selector's `likely_game_logic` is a screening signal, not proof. Manually verify that the function implements real game logic and is not merely an accessor, wrapper, initializer or data helper.

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
