# OpenCode integration

This directory contains the native OpenCode skills for the decompilation workflow.

## Installation

The canonical skills live under `decomp/skills/`. For a truly self-contained OpenCode installation, generate a bundle first:

    python decomp/scripts/package_opencode.py --output D:/xavi/opencode-decomp-skills --force

The generated directory contains one OpenCode skill directory per `SKILL.md` plus a private `_runtime/` directory with the shared helpers. The source repository remains the single source of truth; the bundle is generated output.

On Windows, for example, add this to your global OpenCode config at:

    %USERPROFILE%\.config\opencode\opencode.json

Use an absolute path because relative paths in the OpenCode `skills` array are resolved from the active OpenCode working directory:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": [
    "D:/xavi/opencode-decomp-skills"
  ]
}
```

Replace the path with the location where this repository is cloned.

OpenCode scans the configured source recursively. The generated bundle therefore exposes:

    decomp/skills/ph-decomp/SKILL.md
    decomp/skills/ph-challenge/SKILL.md
    decomp/skills/matching-decomp/SKILL.md
    decomp/skills/ghidra-evidence/SKILL.md
    decomp/skills/reference-decomp/SKILL.md
    decomp/skills/xmap-analysis/SKILL.md

No OpenCode plugin installation command is required: these are native skills loaded through OpenCode's `skill` mechanism.

## Usage

Start a new OpenCode session after changing the skill source or switching branches.

The main skill IDs are:

    /ph-decomp
    /ph-challenge
    /matching-decomp

The supporting skills are:

    /ghidra-evidence
    /reference-decomp
    /xmap-analysis

A skill can also be loaded explicitly by the native `skill` tool using its exact ID.

Prefer `/ph-decomp` for Phantom Hourglass work. It routes the request to the smallest appropriate workflow:

    EXPLAIN -> INSPECT -> ANALYZE -> TARGET_MATCH
                                  \
                                   -> SELECT / CHALLENGE

A named function therefore does not trigger global candidate selection unless the evidence requires it.

## Development

For development, you can point OpenCode directly at `D:/xavi/skills/decomp`. The bundler is preferred for validating the portable installation layout.

To test a branch of this repository with OpenCode:

```powershell
Set-Location D:\xavi\skills
git fetch origin
git checkout feat/decomp-agent-routing-guardrails
git pull
```

Because the configured source points at the working tree, OpenCode will use that checked-out version.

## Helper paths

Every skill keeps its helper references relative to its own `SKILL.md`.

For example, from:

    decomp/skills/ph-decomp/SKILL.md

the shared helpers are:

    ../../scripts/

This matters for portability: OpenCode resolves paths inside a skill relative to the directory that contains `SKILL.md`. Do not reintroduce a host-specific `<skills>/decomp/scripts` placeholder.

The canonical repository layout keeps the skills usable from the existing Codex plugin because the shared scripts remain inside the `decomp` plugin tree. The OpenCode bundle rewrites helper paths to its private `_runtime/` directory.

For OpenCode V2, use ordered `permissions` rules. The native skill permission is separate from shell/edit permissions; session policy files provide an additional repository-level gate for decomp helpers. See `opencode.example.jsonc`.

## Troubleshooting

If a skill is not visible in OpenCode:

1. Verify that the configured source points to `decomp`, not `decomp/skills`.
2. Verify that the target file is exactly `SKILL.md`.
3. Check that the skill ID matches the directory name.
4. Check OpenCode skill permissions if a skill is hidden or denied.
5. Start a fresh session after changing the source.

## References

OpenCode skills documentation:

https://opencode.ai/docs/skills/

OpenCode V2 skills documentation:

https://dev.opencode.ai/v2/docs/skills/
