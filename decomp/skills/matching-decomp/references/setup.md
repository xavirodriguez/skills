# Setup for Matching Decompilation

## Required tools

1. **Ghidra + PyGhidra**
   ```bash
   # Install a recent Ghidra release, then:
   pip install pyghidra
   # Set GHIDRA_INSTALL_DIR if needed
   export GHIDRA_INSTALL_DIR=/path/to/ghidra
   ```

2. **objdiff** — https://github.com/encounter/objdiff  
   Used to compare object files instruction-by-instruction and report match percentage.

3. **ninja** (or the project's build system) that produces the object file containing the target function.

4. Optional but recommended:
   - `m2c` or similar decompiler cleaners for first-pass C cleanup
   - The project's original compiler toolchain (IDO, MWCC, matching GCC version)

## Minimal project layout

```
project/
├── src/
│   └── target.c          # C you are matching
├── include/              # headers with s32, u16, structs, etc.
├── build/
│   └── target.o          # produced by ninja
├── expected/
│   └── target.o          # original object (or extracted from binary)
├── build.ninja / Makefile
└── objdiff.toml          # or CLI flags pointing at build/ and expected/
```

## Typical evaluation command

```bash
ninja && objdiff diff --json --function MyFunction
```

JSON output usually contains a match percentage and a per-instruction diff. Use that as the sole success metric.

## Extracting a function from a full binary

If you only have an ELF/PE and no separate object:

1. Use Ghidra to identify the function bounds.
2. Either:
   - Extract the bytes and assemble them into an expected object, or
   - Configure objdiff / a custom script to compare against the binary slice directly.

Many matching projects (decomp.me, matching decomp repos) already provide the expected objects and the build setup; reuse them when available.

## Quick smoke test of the skill scripts

```bash
# After installing pyghidra
python scripts/extract_decomp.py /path/to/binary.elf main
python scripts/pcode_rename.py /path/to/binary.elf
```

Both should print JSON / cleaned C without errors.
