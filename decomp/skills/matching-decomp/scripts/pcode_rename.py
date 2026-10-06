#!/usr/bin/env python3
"""
Apply light P-code heuristics to rename generic Ghidra locals in `main`.

Useful as a first-pass cleanup after extract_decomp.py when the target is main.
Does not modify the binary on disk; only mutates the in-memory Ghidra program
and prints the cleaned C.

Usage:
    python pcode_rename.py <binary_path>
"""

from __future__ import annotations

import sys


def run(binary_path: str) -> None:
    try:
        import pyghidra
    except ImportError:
        print("[-] pyghidra is not installed. Run: pip install pyghidra")
        sys.exit(1)

    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface
    from ghidra.program.model.data import (
        CharDataType,
        IntegerDataType,
        ParameterImpl,
        PointerDataType,
    )
    from ghidra.program.model.listing import Function
    from ghidra.program.model.pcode import PcodeOp
    from ghidra.program.model.symbol import SourceType
    from ghidra.util.task import ConsoleTaskMonitor

    with pyghidra.open_program(binary_path) as flat_api:
        program = flat_api.getCurrentProgram()
        monitor = ConsoleTaskMonitor()

        symbols = list(program.getSymbolTable().getSymbols("main"))
        if not symbols:
            print("[-] Symbol 'main' not found.")
            return

        main_func = flat_api.getFunctionAt(symbols[0].getAddress())
        print(f"[+] main at {main_func.getEntryPoint()}")

        # Standard ABI signature
        int_dt = IntegerDataType.dataType
        char_pp = PointerDataType(PointerDataType(CharDataType.dataType))
        main_func.setReturnType(int_dt, SourceType.USER_DEFINED)
        main_func.updateFunction(
            None,
            None,
            Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL,
            True,
            SourceType.USER_DEFINED,
            [
                ParameterImpl("argc", int_dt, program),
                ParameterImpl("argv", char_pp, program),
            ],
        )
        print("[+] Signature set to int main(int argc, char **argv)")

        decomp = DecompInterface()
        decomp.openProgram(program)
        results = decomp.decompileFunction(main_func, 60, monitor)
        if not results.decompileCompleted():
            print("[-] Decompilation failed.")
            return

        high = results.getHighFunction()
        GENERIC = ("uVar", "iVar", "pvVar", "local_", "cVar", "puVar", "pVar")

        def try_rename(varnode, new_name: str, reason: str) -> bool:
            if not varnode or not varnode.getHigh() or not varnode.getHigh().getSymbol():
                return False
            sym = varnode.getHigh().getSymbol()
            cur = sym.getName()
            if any(cur.startswith(p) for p in GENERIC):
                sym.setName(new_name, SourceType.USER_DEFINED)
                print(f"    [*] {cur} -> {new_name} ({reason})")
                return True
            return False

        renamed = 0
        for op in high.getPcodeOps():
            opc = op.getOpcode()

            if opc == PcodeOp.CALL:
                addr = op.getInput(0).getAddress()
                called = program.getFunctionManager().getFunctionAt(addr)
                if not called:
                    continue
                name = called.getName()

                if name in ("puts", "strlen", "printf", "strcpy", "strcmp"):
                    if op.getNumInputs() > 1 and try_rename(op.getInput(1), "str_input", f"arg of {name}"):
                        renamed += 1
                if name == "strlen" and try_rename(op.getOutput(), "str_len", "return of strlen"):
                    renamed += 1
                if name in ("open", "socket", "fileno", "accept"):
                    if try_rename(op.getOutput(), "file_fd", f"return of {name}"):
                        renamed += 1
                if name in ("read", "write", "close") and op.getNumInputs() > 1:
                    if try_rename(op.getInput(1), "file_fd", f"fd arg of {name}"):
                        renamed += 1

            elif opc in (PcodeOp.INT_EQUAL, PcodeOp.INT_NOTEQUAL):
                for i in range(1, op.getNumInputs()):
                    node = op.getInput(i)
                    if node.isConstant() and node.getOffset() == 0:
                        other = op.getInput(2 if i == 1 else 1)
                        if try_rename(other, "char_curr", "compared to 0 / NUL"):
                            renamed += 1

        print(f"[+] Renamed {renamed} variable(s)")

        clean = decomp.decompileFunction(main_func, 60, monitor)
        print("\n--- CLEANED C ---")
        print(clean.getDecompiledFunction().getC())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pcode_rename.py <binary_path>")
        sys.exit(1)
    run(sys.argv[1])
