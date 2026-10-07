---
name: reference-decomp
description: Analyze an existing decompilation project as prior work so the agent can reuse solved code and avoid re-decompiling already completed functions.
---

# Reference Decompilation

Use this skill when an existing project for the same game, version, or executable contains decompiled source.

The reference is **context and prior work, not match authority**. Its source should prevent duplicated effort, while the target ROM/binary and authoritative comparison remain the proof.

## Reference: Zelda: Phantom Hourglass

The intended reference project is:

    https://github.com/zeldaret/ph

The project has source under `src/` and `libs/`. Its documented workflow uses `tools/configure.py <eur|usa>`, Ninja and objdiff. Its build output includes `arm9.o.xMAP`, and the source uses `// non-matching` annotations.

## Workflow

1. Locate a local clone of the reference repository.
2. Record the exact reference commit and game version when known.
3. Run `decomp/scripts/analyze_reference_project.py <reference-root>` to build an index.
4. If an XMAP analysis exists, pass `--xmap .decomp-agent/xmap-analysis.json` to correlate functions by address.
5. Before selecting a target, check the reference index:
   - `unmarked` -> **apparently matching**; skip re-decompilation by default.
   - `known_nonmatching_equivalent` -> semantic work is likely already present; focus on code generation/matching.
   - `known_nonmatching` -> reuse the existing implementation/context and continue matching it.
6. Prefer exact address correlations over source-name correlations.
7. If a built reference `report.json`/objdiff result is available, use it as stronger evidence than source annotations.
8. Never claim an exact match solely because the reference source is unmarked.

## Output

Store an artifact such as:

    .decomp-agent/reference/ph-analysis.json

Useful fields include `functions`, `xmap_matches`, `status_counts`, `recommended_action_counts` and `policy`.

## Important distinction

A function can be:
- semantically complete but not machine-code matching;
- apparently matching because it has no `non-matching` marker;
- authoritatively verified as matching by the project's build/diff tooling.

Only the last category is proof.
