# skills

Skills para mis agentes (OpenCode / Codex / Grok).

## matching-decomp

Skill de **matching decompilation**: extrae C con Ghidra/PyGhidra y itera hasta que `objdiff` reporte 100% de match.

### Layout

```
decomp/
├── config.json              # Permissions OpenCode
├── system_prompt.md         # Orquestador autónomo de matching
└── skills/
    └── matching-decomp/
        ├── SKILL.md
        ├── scripts/
        │   ├── extract_decomp.py
        │   └── pcode_rename.py
        └── references/
            ├── compiler-heuristics.md
            └── setup.md
```

### Uso rápido

```bash
python decomp/skills/matching-decomp/scripts/extract_decomp.py binary.elf FunctionName
ninja && objdiff diff --json --function FunctionName
```

Requisitos: PyGhidra (o Ghidra headless), ninja, objdiff. Ver `references/setup.md`.
