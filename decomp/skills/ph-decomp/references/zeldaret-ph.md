# Zelda: Phantom Hourglass reference profile

Reference repository:

    https://github.com/zeldaret/ph

Observed conventions:
- sources: `src/` and `libs/`
- `// non-matching` explicitly marks known machine-code mismatch
- `// non-matching (equivalent)` means semantic equivalence was accepted but machine code still differs
- `// non-matching (regalloc)` identifies a code-generation/register-allocation mismatch
- many function names encode linked addresses, for example `func_0203c72c`
- build output: `build/<eur|usa>/`
- ARM9 linker map: `build/<eur|usa>/arm9.o.xMAP`
- configuration: `tools/configure.py <eur|usa>`
- common verification: `ninja arm9 report check`

Reference policy:
- absence of `non-matching` is apparently matching, never proof
- exact address correlation is stronger than name-only correlation
- reference source supplies prior work and context
- target ROM/Ghidra/XMAP and target objdiff remain authoritative
