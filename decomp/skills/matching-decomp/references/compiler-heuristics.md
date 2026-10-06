# Compiler Heuristics for Matching Decompilation

Apply these rules when `objdiff` shows a mismatch. Always re-compile and re-diff after each change.

## 1. Register swaps / allocation

**Symptom:** Same opcodes, different registers (`$a0` vs `$v0`, `r3` vs `r4`, `eax` vs `ecx`).

**Fixes:**
- Reorder local variable declarations.
- Change evaluation order of expressions (extract sub-expressions into temporaries).
- Introduce or remove intermediate variables to force the compiler to pick different registers.
- Prefer the order that mirrors the original assembly argument-passing sequence.

## 2. Branching and control flow

**Symptom:** Inverted conditions (`beq` vs `bne`), extra jumps, or different basic-block layout.

**Fixes:**
- Switch between `if (cond)` and `if (!cond)`.
- Convert `for` ↔ `while` ↔ `do-while`.
- Move assignments into conditions: `if ((x = get_val()) != 0)`.
- Prefer early returns / early continues when the original has short-circuit paths.
- Avoid introducing extra compound statements that force additional jumps.

## 3. Stack frame and offsets

**Symptom:** Different stack adjustment (`addiu $sp, $sp, -0x20` vs `-0x18`), wrong local offsets.

**Fixes:**
- Change local types (e.g. `s16` ↔ `s32`, add/remove padding).
- Add or remove explicit blocks `{ ... }` to alter variable lifetime/scope.
- Adjust the number of live locals; dead stores can still affect frame size on some compilers.
- Check alignment requirements of the target ABI (MIPS o32, PPC EABI, etc.).

## 4. Instruction choice and immediates

**Symptom:** Different instructions for the same constant or memory access (`li` vs `addiu`, `lw` vs `lhu`, extra shifts).

**Fixes:**
- Cast constants explicitly: `(u32)0xFFFF`, `(s16)value`.
- Cast pointers before arithmetic: `((u8 *)ptr) + offset`.
- Mark variables `volatile` only when the original reloads from memory unnecessarily.
- Prefer the exact type width the original uses (halfword loads vs word loads).
- On MIPS, be aware of `lui`/`ori` pairs vs `li` macro expansion differences between assemblers.

## 5. Calls and argument passing

**Symptom:** Wrong register for an argument, extra move before call, missing delay-slot fill.

**Fixes:**
- Match the exact argument evaluation order of the original compiler.
- Avoid temporaries that force spills when the original kept the value in a register.
- For varargs or floating-point args, follow the ABI strictly (MIPS o32, System V, etc.).

## 6. Compiler-specific notes

### IDO (N64 / IRIX)
- Very sensitive to declaration order and expression complexity.
- Prefer simple statements; complex expressions often produce different register allocation.
- `#pragma` and `__builtin` usage can change codegen dramatically.

### Metrowerks MWCC (GameCube / Wii)
- Aggressive inlining and scheduling.
- Stack alignment and padding differ from GCC.
- Prefer the project's existing macros for common patterns.

### GCC 2.x / 3.x
- `-O1` / `-O2` produce very different code.
- Schedule and register allocation are deterministic for a given version + flags.
- Match the exact GCC version used by the original project when possible.

## Workflow tip

When multiple heuristics could apply, change **one thing at a time**, re-run `objdiff`, and keep the change only if the match percentage improves or the mismatched instruction count decreases.
