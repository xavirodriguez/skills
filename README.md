# skills

Skills para mis agentes (OpenCode / Codex / Grok).

## matching-decomp

Skill para **matching decompilation** de juegos y software legacy: Ghidra/PyGhidra + evidencia estructurada + hipótesis de código fuente + build/compare reproducible.

### Flujo

```
inspect -> scout -> analyze -> propose -> dry-run -> apply one change
  -> build -> authoritative compare -> parse -> ledger -> repeat
```

### Herramientas

- `decomp/skills/matching-decomp/SKILL.md` — skill principal.
- `decomp/system_prompt.md` — prompt para el agente.
- `decomp/scripts/inspect_project.py` — descubre señales de build/decomp.
- `decomp/scripts/scout_functions.py` — prioriza funciones candidatas en Ghidra.
- `decomp/scripts/analyze_function.py` — genera evidencia JSON de una función.
- `decomp/scripts/run_match.py` — ejecuta build/compare explícitos de forma controlada.
- `decomp/scripts/parse_compare.py` — extrae evidencia de logs de comparación.
- `decomp/MANUAL.md` — manual completo con workflow de Klonoa: Empire of Dreams.

### Uso mínimo

```bash
python3 decomp/scripts/inspect_project.py /path/to/project
```

Después de inspeccionar el proyecto, el agente debe descubrir y usar sus comandos reales de build/compare. No se asumen Ninja, Make, objdiff ni un ABI concreto.

### Principios

- Assembly es la evidencia final.
- El decompiler C es una hipótesis.
- Un scout score nunca demuestra un match.
- Un cambio por iteración.
- El compare autoritativo decide el éxito.
- Los logs y el hypothesis ledger hacen el proceso reproducible.

La implementación de esta iteración está documentada en `decomp/MANUAL.md`.
