# Compiler Heuristics for Matching Decompilation

Apply these rules when `objdiff` (or `make compare`) shows a mismatch. Always re-compile and re-diff after each change. Change **one thing at a time**.

---

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

## 6. Compiler-specific notes (legacy)

### IDO (N64 / IRIX)
- Very sensitive to declaration order and expression complexity.
- Prefer simple statements; complex expressions often produce different register allocation.
- `#pragma` and `__builtin` usage can change codegen dramatically.

### Metrowerks MWCC (GameCube / Wii)
- Aggressive inlining and scheduling.
- Stack alignment and padding differ from GCC.
- Prefer the project's existing macros for common patterns.

### GCC 2.x / 3.x (generic)
- `-O1` / `-O2` produce very different code.
- Schedule and register allocation are deterministic for a given version + flags.
- Match the exact GCC version used by the original project when possible.

---

## 7. agbcc / Thumb (GBA — ARM7TDMI)

agbcc is GCC 2.95 targeting Thumb. Semantically identical C often produces different bytes depending on **how the source is spelled**. Prefer plain-C levers over `asm("")` barriers. A barrier is unfinished work, not a match-with-caveat.

Typical flags: `-mthumb-interwork -O2 -fhex-asm -fprologue-bugfix` (game code); `old_agbcc` for some SDK modules (m4a).

Verify with the project's full-ROM check (`make compare`), not only per-function objdiff — agbcc couples codegen across a translation unit.

### 7.1 Named extern vs cast address constant

Highest-value lever. Same numeric address, different codegen:

```c
extern const u8 gBgLayerLookup[][2][2];   /* symbol_ref — keep address live across loop/call */
((const u8 (*)[2][2])0x08057ACC)         /* CONST_INT — rematerialise / strength-reduce */
```

- Symbol form: compiler keeps the address in a callee-saved register.
- Constant form: prefers rematerialisation or pointer induction (`adds rN, #2` per iteration).

**Corollary:** if a table only exists as `#define ADDR 0x08xxxxxx`, promote it to a real `extern` in a header + linker script entry. Often the whole match.

### 7.2 Multi-dimensional array shape

Declaring dimensions changes address arithmetic:

```c
extern const u8 gBgLayerLookup[][2][2];  /* folds +1 into the symbol: adds r0, r4, #1 */
extern const u8 gBgLayerLookup[];        /* separate ldrb r0, [r0, #1] */
```

- A 2-byte struct is **not** equivalent: ARM `STRUCTURE_SIZE_BOUNDARY` is 32 bits, so `struct { u8 a; u8 b; }` pads to 4 and emits wrong stride.
- Prefer flat or multi-dimensional arrays of `u8` / `s16` when the ROM indexes that way.
- Struct of scalars vs run-time-indexed array: member offset may fold into `strh r0, [r1, #8]` while indexing computes `base + 8` as a value and stores at offset 0.

### 7.3 Bitfield container type

For `field ^= K`, the **container type of the group** changes the insert mask:

| container | codegen |
|-----------|---------|
| `u8` | `movs r0, #M` + `negs r0, r0` |
| `u32` | CSE against the register holding K: `movs r0, #K` … `subs r0, #n` |

Choose per group inside one struct. Changing one group can break a neighbouring already-matched function — re-run full compare after any bitfield change.

Note: a byte mask is not a field value. A 2-bit field at bit offset 1 with `^= 2` toggles the field's high bit (byte bit 2), not necessarily the `0x02` flag.

### 7.4 Do not cache a global in a local (usually)

Many stream/IO helpers only match when the global is **re-read** at each use:

```c
/* Match: re-read */
gStreamPtr[2]  /* in each switch arm */

/* Mismatch: cache */
u8 b = gStreamPtr[2];  /* collapses arms, wrong block layout */
```

Refinements:
- **Pointer local is OK:** `u8 *p = gStreamPtr; … p[2]` still matches.
- **Value caching is load-bearing.** Caching both table bytes can collapse the prologue (`push {lr}` vs `push {r4, r5, lr}`).
- **MMIO inverts the rule:** a second read of a hardware register (`REG_VCOUNT_L`) is a real second load — cache in a local is often **mandatory**.

### 7.5 Operand order

Commutative in C, not in the output:

- **Index terms:** write the *varying* term first to suppress strength reduction of the address into a pointer induction variable.
  - `table[i * 2 + scene * 4]` vs `table[scene * 4 + i * 2]` can differ by ~8–19 instructions.
- **Multiplication:** `a * b` vs `b * a` can change which of `ldrh`/`ldrb` is emitted first (2-instruction gap).

Copying operand order from a matching neighbour can point the *wrong* way — measure on the target function.

### 7.6 Intermediate width

Declared width of a temporary decides pool load vs synthesised constant:

```c
u16 mask = 0xFFF7;   /* often: load from literal pool (what the ROM does) */
s32 mask = 0xFFF7;   /* often: mov r3, #9 / neg r3, r3 */
```

Sometimes a `u16` local holding a constant is required for its own sake — inlining the constant at both call sites breaks the match.

### 7.7 Stack frame layout (size, not declaration order)

- A `u16` local goes to `sp+0` and a `u32` to `sp+4` **regardless of declaration order**.
- Two locals of the *same* size follow declaration order.
- An aggregate is not a substitute for two independent locals: `struct { u32; u16; }` can give right offsets but wrong addressing (`strh r0, [r3, #4]` pinned to `sp` vs `add r0, sp, #4` reused).

### 7.8 Extern symbols vs `#define` address barriers

Replace integer address constants with linker symbols when you need a natural `ldr rN, =symbol` through the literal pool:

```c
/* Bad for matching: CONST_INT, may fold or schedule freely */
#define ROM_TABLE 0x08118AB4
u32 addr = ROM_TABLE;
asm("" : "=r"(table) : "0"(addr));

/* Good: extern + ldscript symbol */
extern const struct Song gSongTable[];
const struct Song *songTable = gSongTable;  /* ldr via pool */
```

When extern is **not** enough:
1. Load must occur at a very specific instruction position (compiler hoists earlier).
2. Register assignment of the loaded address matters.
3. Need base + offset form (`ldr r1, =sym; str r0, [r1, #4]`) not folded (`ldr r1, =(sym+4)`).

### 7.9 Barriers and register pins (prefer removing them)

Three common patterns — treat as temporary, not final:

| Pattern | Purpose | Prefer instead |
|---------|---------|----------------|
| `asm("" : "=r"(ptr) : "0"(addr))` | Force address load point | named `extern` / pointer local |
| `asm("" : "+r"(shifted))` | Stop `(x<<N)>>M` fold into `x<<(N-M)` | often irreducible if `ldr`s must interleave |
| `register T var asm("rN")` | Pin register | declaration order, shared loads, project macros |

Removable pin patterns:
- **Address held across a call:** declare a plain pointer local *before* the call so its live range spans the `bl` → agbcc picks callee-saved (r4+) on its own.
- **Pin faking a redundant move:** usually a *shared load* — bind the re-read to one named local and use it for every consumer in that window.
- **Hand-rolled DMA pointer:** replace with canonical `DmaCopy16` / `DmaFill16` / `DmaCopy32` macros; they allocate registers the way the original did.

Keep a barrier only when measured irreducible (e.g. shift pair with mandatory interleaved loads). Document why.

### 7.10 Orphan blocks `{ }`

C89 requires declarations at block start. Orphan blocks appear for:
1. Mid-function variables — hoist to function top if register allocation still matches.
2. Register lifetime control — block ends lifetime so a later local reuses the register.

Test by removing/moving the block and re-comparing.

### 7.11 What does *not* matter (agbcc)

- `~FLAG` vs literal mask on `vu16` registers (`REG_IE &= ~IE_VBLANK` ≡ `&= 0xFFFE`).
- XOR operand order (`v ^ 2`, `2 ^ v`, `^= FLAG`) — agbcc canonicalises.
- Many agent/instrumentation flags are byte-neutral (project-specific).

### 7.12 Full-ROM coupling

A function can be byte-exact in isolation and still break another function later in the **same `.c`** (e.g. referencing an extern symbol perturbs a neighbour 1800 lines down). Always run the full-ROM check after adding a match, not only the single-function score.

---

## Workflow tip

When multiple heuristics could apply, change **one thing at a time**, re-run the diff, and keep the change only if match percentage improves or mismatched instruction count decreases. For GBA projects, prefer `make compare` over isolated objdiff after every successful function match.
