name: ghidra-reverse
description: Free and open-source reverse engineering and matching decompilation with Ghidra...

1. [Invocación]
   Agent -> Bash: python .opencode/skills/ghidra-reverse/scripts/extract_decomp.py target.elf Player_Update
   
2. [Extracción]
   PyGhidra abre el ELF de forma headless -> Decompila -> Devuelve código C bruto stdout.

3. [Normalización]
   Agent -> Aplica m2c / limpiador LLM para adaptar sintaxis al compilador original (ej. MWCC / IDO).
   Agent -> Escribe C candidato en src/player.c.

4. [Evaluación & Bucle]
   Agent -> Bash: ninja build/player.o && objdiff diff --json --function Player_Update
   Agent -> Lee el porcentaje de match y el diff de instrucciones.
   Agent -> Si match < 100%, reajusta el C y repite la compilación.