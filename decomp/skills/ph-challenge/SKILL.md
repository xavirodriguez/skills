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

Determine the requested operation from the user's input before doing any work:
- `Tier 1`, `Tier 2`, or `Tier 3` selects that challenge workflow directly;
- a named function or candidate selects targeted matching/inspection for that function;
- `verify Tier N` selects verification only;
- ask one clarification question only when the requested operation cannot be determined from the user input.

Once the operation is determined, do not ask the user to choose again. Continue autonomously until the next explicit decision point or a real infrastructure blocker.

For a named candidate or a question about an existing candidate pack:
- use targeted inspection/analysis;
- do not regenerate the global report, scout population or reference gate unless the user asks for a fresh selection or the evidence is stale/missing;
- never edit or build merely because a challenge skill is active.

Honor explicit constraints such as "explain first", "do not edit", or "do not compile yet" before advancing phases.

For autonomous selection, use the full objective pipeline and keep complete reports under `.decomp-agent/` while exposing only compact summaries in context.

Use this skill when the goal is the decomp challenge, not merely general PH decompilation.

## Autonomous batch controller

When the user asks for autonomous solving, multiple matches, a batch, or to continue with the next function after a match, use the persistent batch controller instead of treating the challenge as a single-target task.

Initialize or resume the queue:

    <python> ../../scripts/challenge_batch.py init --project . --report .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --reference .decomp-agent/reference/ph-analysis.json --tier tier2 --quota 0 --max-stagnation 3 --policy .decomp-agent/session-policy.json --require-policy

`--quota 0` means continue until there are no eligible candidates or a real blocker. Use a positive quota only when the user explicitly requests a bounded number of matches.

Get the next target:

    <python> ../../scripts/challenge_batch.py next --session .decomp-agent/challenge/session.json --claim

For the active target, follow the normal matching-decomp loop. Run exactly one source hypothesis/change per iteration, then use `run_match.py` with the project's authoritative build and compare commands and the active session policy.

After each experiment, record the authoritative result:

    <python> ../../scripts/challenge_batch.py record --session .decomp-agent/challenge/session.json --target <candidate> --before <match-before> --after <match-after> [--mismatch "<first mismatch>"] [--lesson "<compact lesson>"]

For an exact match, use `--exact` together with the authoritative report refresh command. The controller then refreshes the report and rescales/rescores the queue as one success transition:

    <python> ../../scripts/challenge_batch.py record --session .decomp-agent/challenge/session.json --target <candidate> --before <match-before> --after 100 --exact --refresh-command "<authoritative report/build command>" --report .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --reference .decomp-agent/reference/ph-analysis.json --project . --policy .decomp-agent/session-policy.json --require-policy

After the exact-match transition, collect object/link integration evidence and record it:

    <python> ../../scripts/challenge_batch.py integration-record --session .decomp-agent/challenge/session.json --target <candidate> --status pass --evidence .decomp-agent/integration/<candidate>.json --policy .decomp-agent/session-policy.json --require-policy

Then run the authoritative refresh before asking for the next target:

    <python> ../../scripts/challenge_batch.py refresh --session .decomp-agent/challenge/session.json --project . --refresh-command "<authoritative report/build command>" --report .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --reference .decomp-agent/reference/ph-analysis.json --policy .decomp-agent/session-policy.json --require-policy
Rules:
- An exact function match enters `integration-pending`; it does not clear the active target and does not increment `matches_completed`.
- Integration `pass` enters `refresh-required`; it still does not clear the active target.
- The authoritative report refresh is mandatory. Only after refresh may the controller finalize the target as `matched`, clear `current_target`, increment `matches_completed` and select the next candidate.
- A positive match delta resets stagnation.
- A non-improving experiment increments stagnation.
- When stagnation reaches the configured threshold, the candidate is automatically marked `blocked` and the controller can move to the next candidate.
- Infrastructure blockers halt the session; they must not be silently converted into candidate skips.
- A candidate that becomes partial after an edit remains the active target until it reaches exact match or is blocked. Do not lose it merely because it no longer satisfies the original zero-match selector gate.

Then claim the next candidate and continue without asking the user again:

    <python> ../../scripts/challenge_batch.py next --session .decomp-agent/challenge/session.json --claim

Do not use a fixed total experiment count as the stopping condition. Stop because:
- the requested quota is reached;
- no eligible candidates remain;
- the current candidate is stagnant and has been auto-blocked, after which the next candidate is selected;
- or a real infrastructure blocker halts the session.

### Match and integration state

A function-level exact match is a transition, not the end of the target lifecycle:

    MATCH_EXACT
        -> INTEGRATION_CHECK
            -> INTEGRATION_PASS -> refresh -> next candidate
            -> INTEGRATION_MISMATCH -> keep current target -> fix integration
            -> INTEGRATION_BLOCKER -> halt session

When a target reaches 100%, `challenge_batch.py` must leave it in `integration-pending`. Do not claim the next candidate until the authoritative object/link integration check passes.

Keep these locations separate in notes and candidate summaries:

- function entry/size: the machine-code function itself;
- translation unit/object: the containing object/source unit;
- integration range: the linker/delink range being verified;
- padding: bytes owned outside the function body but inside the integration range.

Never describe an object/range boundary as the function address. Never mirror a USA/EUR integration change without independent evidence for each region.

Integration evidence should be recorded with:

    python ../../scripts/challenge_batch.py integration-record       --session .decomp-agent/challenge/session.json       --target <function>       --status pass       --evidence .decomp-agent/integration/<target>.json       --policy .decomp-agent/session-policy.json --require-policy

### Experiment execution guardrails

For every candidate experiment, use this execution contract:

1. Edit source only through `../../scripts/source_edit.py`; never call `apply_patch` from a shell and never invoke another coding agent.
2. Build and compare only through `../../scripts/run_match.py`.
3. Prefer `../../scripts/compare_target.py` as the compare command so objdiff runs in report/JSON mode instead of an interactive diff UI.
4. A transport/tooling failure is recorded with `challenge_batch.py record --tool-transport-failure`. It keeps the target active and does not consume stagnation.
5. Only compiler/linker failures caused by the current source hypothesis and authoritative compare deltas count as experiment evidence.

The agent must not use a direct `objdiff-cli diff` invocation in the autonomous loop.

### Deterministic Tier 2 execution

After claiming a candidate, do not manually re-rank or switch targets. The controller owns target selection.

For each iteration:

    inspect evidence
      -> write ONE hypothesis
      -> source_edit.py
      -> git diff verification
      -> run_match.py
      -> parse structured compare result
      -> challenge_batch.py record
      -> continue same target

Decision rules:

- compare_target.py valid JSON + exact: record exact, enter integration verification.
- valid JSON + partial/zero: record result and diagnose the first mismatch family.
- build/compare timeout or transport failure: record --tool-transport-failure; do not consume stagnation.
- compiler/linker failure caused by the current source edit: record experiment evidence and continue with a new hypothesis.
- missing helper/project path: one existence check, then stop on absence.
- candidate analysis is incomplete: gather bounded evidence for the same candidate; never rotate because it is inconvenient.
- optional context-pack/reporting failure: do not reinterpret the target; continue only when required evidence remains available.
- never use skip as a convenience mechanism for selecting an easier candidate.

The next candidate may only come from:

    challenge_batch.py next --session ... --claim

and only after the current target has reached the terminal matched state.
### Tier 2 selection contract

Selection must be derived from the current authoritative report and current Ghidra/XMAP evidence.

- Existing selection artifacts are cacheable context only, never the source of truth.
- Before reusing an artifact, validate its provenance with `validate_selection.py`.
- If provenance is missing or stale, regenerate from the current authoritative inputs, unless the user explicitly forbids writes; in that case rank directly from the authoritative inputs without claiming the old artifact is current.
- Missing match data is `unknown`; it must not be converted to `0%` and must not satisfy the zero-match Tier 2 gate.
- A failed read of a plugin-cache skill file is not a project/infrastructure blocker. Do not scan arbitrary cache or drive locations to replace it.
- Selection does not claim that a candidate is executable or matchable. It only produces an ordered evidence-backed ranking.

### Post-milestone strategic reselection

After a meaningful exact-match milestone, recompute the strategic next target rather than continuing to use the previous Tier 2 ordering.

Run the read-only ROI selector:

    <python> ../../scripts/roi_selector.py \
      .decomp-agent/challenge/report.json \
      --scout .decomp-agent/challenge/tier2-scout.json \
      --project . \
      --reference .decomp-agent/reference/ph-analysis.json \
      --top 5 \
      -o .decomp-agent/challenge/roi-selection.json

When available, pass the previous authoritative report with \`--previous-report\`. The helper reports newly completed translation units and newly exact functions so the selection can explicitly account for the changed knowledge state.

ROI selection is separate from the mechanical Tier 2 gate. It answers which unresolved function should be attacked next for maximum useful progress, not which function merely satisfies the challenge threshold.

For each candidate evaluate:

    EASE
    IMPACT
    UNLOCK
    ROI = EASE * IMPACT / 100

Prefer high ROI, then use UNLOCK to break ties and justify candidates that can establish reusable anchors, structures, globals or call patterns.

A refreshed authoritative report changes the provenance hash. Treat a previous ROI selection as stale after such a refresh and regenerate it before using the ranking.

Do not edit, build or compare candidates during ROI selection. The selected target must still pass the normal matching/decompilation and challenge gates before execution.

## Candidate ranking

The selector exposes `expected_value_score` in addition to `success_score`, `game_logic_score` and `complexity_score`.

`expected_value_score` is a transparent heuristic, not a probability. It favors candidates that combine higher estimated success potential, stronger game-logic evidence, lower estimated matching complexity, and enough code size to make the effort worthwhile.

Within the eligible set, use expected value as the primary ordering signal. Do not blindly choose the largest function.

## Evidence and lesson reuse

Before deep analysis of each candidate, prepare/load its candidate pack so prior lessons are surfaced automatically. Reuse prior hypotheses only as evidence; prefer lessons with matching mismatch families or similar signatures, and never copy an old source change blindly.

## 1. Challenge gate: decide admissibility before heavy work

For an explicit Tier request, check the minimum admission evidence before running a clean rebuild, global scout, published-progress lookup, or other expensive baseline work.

At minimum:
- Tier 1: establish whether an exact candidate is being verified or selected;
- Tier 2: verify the Tier 2 mechanical gates before matching;
- Tier 3: verify that a solid Tier 1 exact result and a solid Tier 2 exact result are already recorded.

If a required prerequisite is missing, stop after collecting only the evidence needed to prove the blocker. Do not continue into target matching or expensive global analysis.

For Tier 3, the prerequisite is exact authoritative completion evidence for both Tier 1 and Tier 2. A high fuzzy percentage, semantic similarity, or a partial prior attempt does not satisfy the gate.

Published progress from decomp.dev is contextual provenance only. Do not block a challenge solely because local fork progress differs from the published percentage; reconcile the provenance in the final summary instead.

## 2. Establish a clean baseline

For autonomous challenge work that passes the admission gate, materialize the permission budget first:

    <python> ../../scripts/session_policy.py init --mode challenge --force

All autonomous selectors then receive:

    --policy .decomp-agent/session-policy.json --require-policy

Run the PH preflight first. Then follow the project's own README/INSTALL and verify a clean build.

Record:
- game version;
- local matched percentage;
- local function count;
- report path and generation command;
- relevant contribution rules.

Do not require local progress numbers to equal decomp.dev. Record any fork/upstream provenance difference as context, not as an admission blocker.

## 3. Generate authoritative progress data

Use the project's normal build/compare workflow and generate an objdiff v2 report with the installed `objdiff-cli` when the project supports it.

Do not infer function match status from source comments, filenames, or Ghidra names when an authoritative report is available.

For the selector, preserve the report as:

    .decomp-agent/challenge/report.json

## 4. Generate targeted Tier 2 Ghidra evidence

For Tier 2, do not use the generic top-100 scout: large functions can be penalized by its ranking and omitted.

Run the targeted Ghidra scout against the authoritative report:

    <ghidra> ... -postScript tier2_ghidra_scout.py .decomp-agent/challenge/report.json > .decomp-agent/challenge/tier2-scout.json

It computes the same P75 size gate and analyzes only functions that already satisfy:

    match == 0
    size >= max(256, P75)

The output contains CFG, branch/loop/switch evidence, calls, globals, stores, and signatures.

The scout is evidence only. objdiff remains authoritative.

## 5. Run the unified Tier 2 selector

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

## 6. Tier 1

Prefer a small, clearly undecompiled function that is not an obvious stub/table/data function.

Before editing:
- verify it is genuinely undecompiled in objdiff;
- inspect its Ghidra disassembly/decompiler;
- identify the source file and contribution style;
- preserve the baseline evidence.

Then use `matching-decomp` and require an exact byte match.

## 7. Tier 2

A Tier 2 target must satisfy every gate:

    match_percent == 0
    size >= 256 bytes
    size >= P75(remaining undecompiled sizes)
    confirmed control flow
    not an obvious stub/table/data function

"Confirmed control flow" requires Ghidra scout evidence (`has_branch`, `has_loop`, or `has_switch`).

The engine's game_logic_score is a screening signal, not proof. Manually verify that the function implements real game logic and is not merely an accessor, wrapper, initializer or data helper.

Choose the highest expected-value candidate among the eligible set rather than blindly choosing the largest one.

## 8. Tier 3

Only attempt Tier 3 after Tier 1 and Tier 2 are solid.

Treat the Tier 3 gate as satisfied only when exact authoritative completion evidence exists for both previous tiers. A prior fuzzy match, a nearly matching implementation, or an undocumented manual result is insufficient.

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

Do not retry the same failed command more than once unless the retry changes the diagnosis, invocation, environment, or hypothesis.

Optional documentation, telemetry, or note-writing failures must not turn into repeated attempts or block an otherwise complete challenge decision. Report the artifact failure and continue when the required evidence is already available.

If a patch/edit transport mechanism fails, treat that as an infrastructure or tooling error: do not resend the same malformed patch repeatedly. Either correct the mechanism once or skip the optional artifact and proceed.

## Context discipline

Keep authoritative reports and scout JSON on disk. Read only summary fields, the selected candidate, or target-specific evidence needed for the current decision. Never truncate by position ("first three") when relevance filtering can identify the correct records.

## 9. Matching loop

For each chosen function:

    analyze -> hypothesis -> one source change -> dry-run -> build -> compare

Only an exact authoritative match counts as success.

Never call 99% or semantic equivalence a match.

## 10. Deliverable check

Before opening a PR:
- reread `CONTRIBUTING.md` and relevant project docs;
- verify formatting;
- verify the exact function matches;
- ensure only intended changes are included;
- disclose AI assistance when the challenge asks for it and the project's rules allow a contribution.

Keep the selector output and matching evidence available as part of your challenge notes.
