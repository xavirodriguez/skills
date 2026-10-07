# Zelda: Phantom Hourglass reference profile

Repository:

    https://github.com/zeldaret/ph

Current project conventions to exploit:

- Source roots: `src/`, `libs/`
- Function status annotations: `// non-matching`
- More specific annotations include `// non-matching (equivalent)` and `// non-matching (regalloc)`
- ARM/Thumb mode is written on function definitions as `ARM` or `THUMB`
- Many function names encode their linked address, for example `func_0203c72c` or `func_ov014_02144820`
- Build output: `build/<eur|usa>/`
- ARM9 linker map: `build/<eur|usa>/arm9.o.xMAP`
- Build configuration: `tools/configure.py <eur|usa>`
- Typical CI verification invokes `ninja arm9 report check`
- `objdiff.json` and `report.json` are generated artifacts, not repository source files

Interpretation policy:

- `// non-matching` is explicit evidence that the implementation still differs.
- `// non-matching (equivalent)` means the authors consider it semantically equivalent but it still does not match; do not redo semantic analysis unless target evidence contradicts it.
- Absence of a marker means apparently matching, not mathematical proof.
- Prefer an authoritative objdiff/build report when available.
- Never let reference source overwrite evidence from the target ROM, target XMAP or target Ghidra analysis.
