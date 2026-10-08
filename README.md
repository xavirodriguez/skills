# skills

Skills para mis agentes (OpenCode / Codex / Grok).

## Codex plugin

Este repositorio incluye un marketplace de Codex que publica `decomp` como plugin.

### Instalación

```powershell
codex plugin marketplace add xavirodriguez/skills
codex plugin add decomp@xavi-skills
```

También puedes fijar una rama concreta durante el desarrollo:

```powershell
codex plugin marketplace add xavirodriguez/skills --ref <branch>
```

Después de instalar o actualizar un plugin, inicia un hilo nuevo de Codex para cargar la versión actualizada.

## OpenCode

La integración de OpenCode usa **skills nativas**, no un plugin de OpenCode.

Consulta [decomp/OPENCODE.md](decomp/OPENCODE.md) para la instalación. La configuración mínima es añadir el directorio `decomp` como fuente de skills:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": [
    "D:/path/to/skills/decomp"
  ]
}
```

OpenCode descubre los `SKILL.md` anidados dentro de esa fuente y las rutas de los helpers son relativas a cada skill. Los IDs principales son `ph-decomp`, `ph-challenge` y `matching-decomp`.

En OpenCode V2 se pueden activar explícitamente desde el catálogo como `/ph-decomp`, `/ph-challenge` y `/matching-decomp`.


## ph-challenge

Workflow específico para el challenge de decompilación de Phantom Hourglass.

Calcula y documenta automáticamente:

- funciones restantes sin decompilar según el reporte autoritativo de objdiff;
- P75 del tamaño de las funciones restantes;
- candidatos Tier 1;
- candidatos Tier 2 que cumplen 256 bytes + P75 + control flow;
- candidatos Tier 3 ordenados por señales objetivas de dificultad.

Uso:

```powershell
<python> decomp/scripts/challenge.py .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --project . --top 10 -o .decomp-agent/challenge/tier2-selection.json
```

El selector no decide por sí solo si una función contiene lógica de juego real: esa comprobación requiere inspección manual.



### OpenCode packaging

For a self-contained OpenCode installation, generate the native skill bundle:

```powershell
python decomp/scripts/package_opencode.py --output D:\\xavi\\opencode-decomp-skills --force
```

Then point OpenCode's `skills` array at that generated directory. The repository remains the single source of truth; the generated bundle contains the shared runtime helpers inside the OpenCode skill source.

## matching-decomp

Skill para **matching decompilation** de juegos y software legacy: Ghidra/PyGhidra + evidencia estructurada + hipótesis de código fuente + build/compare reproducible.

### Flujo

El agente primero clasifica la tarea. Las consultas puntuales no activan el pipeline completo: EXPLAIN/INSPECT/ANALYZE/TARGET_MATCH usan solo las herramientas necesarias; SELECT/CHALLENGE activan los gates globales.

```
inspect -> scout -> analyze -> propose -> dry-run -> apply one change
  -> build -> authoritative compare -> parse -> ledger -> repeat
```

### Herramientas

- `decomp/skills/matching-decomp/SKILL.md` — skill principal.
- `decomp/skills/ph-decomp/SKILL.md` — entry-point para Phantom Hourglass.
- `decomp/system_prompt.md` — prompt para el agente.
- `decomp/scripts/inspect_project.py` — descubre señales de build/decomp.
- `decomp/scripts/tier2_ghidra_scout.py` — filtra y mide funciones que ya cumplen el tamaño Tier 2.
- `decomp/scripts/challenge.py` — motor unificado de selección y scoring.
- `decomp/scripts/prepare_candidate.py` — genera el pack de contexto para Codex.
- `decomp/scripts/scout_functions.py` — prioriza funciones candidatas en Ghidra.
- `decomp/scripts/analyze_function.py` — genera evidencia JSON de una función.
- `decomp/scripts/run_match.py` — ejecuta build/compare y mantiene el ledger de experimentos.
- `decomp/scripts/parse_compare.py` — extrae evidencia estructurada de logs de comparación.
- `decomp/scripts/parse_xmap.py` — analiza linker maps/XMAP.
- `decomp/scripts/candidate_gate.py` — filtra evidencia de referencia por función.
- `decomp/MANUAL.md` — manual completo del workflow.

### Uso mínimo

```bash
python3 decomp/scripts/inspect_project.py /path/to/project
```

En Windows, usa el intérprete detectado por el preflight y comandos PowerShell, no `python3` por defecto.

Después de inspeccionar el proyecto, el agente debe descubrir y usar sus comandos reales de build/compare. No se asumen Ninja, Make, objdiff ni un ABI concreto.

### Principios

- Assembly es la evidencia final.
- El decompiler C es una hipótesis.
- Un scout score nunca demuestra un match.
- Un cambio por iteración.
- El compare autoritativo decide el éxito.
- Los logs y el hypothesis ledger hacen el proceso reproducible.
- Las restricciones explícitas del usuario limitan edición, build, compare y cambios de worktree.
- Los errores de infraestructura se detienen; los errores derivados de una hipótesis de código se tratan como evidencia.

La implementación está documentada en `decomp/MANUAL.md`.

La integración con OpenCode está documentada en `decomp/OPENCODE.md`. Las políticas de sesión y el histórico de hipótesis se aplican también a los helpers autónomos.


### Tier 2 automatizado

Pipeline recomendada:

    report.json
        -> tier2_ghidra_scout.py
        -> challenge.py
        -> prepare_candidate.py
        -> Codex
        -> run_match.py
        -> objdiff

El selector usa el reporte autoritativo para match, calcula el P75 de las funciones zero-match restantes, comprueba control flow y prioriza candidatos con success score y game-logic score.

Ejemplo:

    <python> decomp/scripts/challenge.py .decomp-agent/challenge/report.json --scout .decomp-agent/challenge/tier2-scout.json --project . --top 10 -o .decomp-agent/challenge/tier2-selection.json

    <python> decomp/scripts/prepare_candidate.py .decomp-agent/challenge/tier2-selection.json <candidate> --project . --compare-json .decomp-agent/challenge/compare-<candidate>.json --scout-json .decomp-agent/challenge/tier2-scout.json

El pack contiene el contexto disponible para el agente y un prompt corto. La preparación no ejecuta objdiff ni abre una interfaz interactiva; el resultado de comparación debe proceder de compare_target.py. La clasificación final de real game logic sigue requiriendo revisión.
