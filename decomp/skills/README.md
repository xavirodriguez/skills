# Decomp skill packaging

\`decomp/skills/\` is the canonical source tree for agent skills.

Each published skill has exactly one:

    <skill-name>/SKILL.md

The frontmatter \`name\` must equal the containing directory name and use the portable lowercase kebab-case format.

## Sources of truth

- \`matching-decomp/SKILL.md\` — generic matching-decompilation policy and experiment loop.
- \`ph-decomp/SKILL.md\` — Phantom Hourglass orchestration and PH-specific gates.
- \`ph-challenge/SKILL.md\` — challenge selection and verification.
- \`ghidra-evidence/SKILL.md\` — read-only Ghidra evidence collection.
- \`reference-decomp/SKILL.md\` — reference project analysis.
- \`xmap-analysis/SKILL.md\` — XMAP analysis and correlation.

Shared runtime helpers live once in \`decomp/scripts/\`. Do not copy them into individual skills in the canonical repository.

For OpenCode, use \`decomp/scripts/package_opencode.py\` to generate a self-contained skill source. The generated bundle puts shared helpers under \`_runtime/\`, so the canonical source remains deduplicated.

## Loading model

OpenCode loads a skill body on demand; secondary skills should be loaded only when their phase is reached.

Codex uses the plugin manifest and discovers the same canonical \`SKILL.md\` files under \`decomp/skills/\`.

Avoid defining the same skill ID in multiple source trees unless the duplication is an intentional override.
