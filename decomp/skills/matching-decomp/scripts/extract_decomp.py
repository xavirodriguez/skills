#!/usr/bin/env python3
"""
Extract decompiled C for a named function from a binary using PyGhidra.

Usage:
    python extract_decomp.py <binary_path> <function_name>

Output: JSON on stdout with keys function, address, c_code
        or {"error": "..."} on failure.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: extract_decomp.py <binary_path> <function_name>"}))
        sys.exit(1)

    binary_path = sys.argv[1]
    target_func = sys.argv[2]

    try:
        import pyghidra
    except ImportError:
        print(json.dumps({
            "error": "pyghidra is not installed. Run: pip install pyghidra"
        }))
        sys.exit(1)

    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor

    with pyghidra.open_program(binary_path) as flat_api:
        program = flat_api.getCurrentProgram()
        decomp = DecompInterface()
        decomp.openProgram(program)
        monitor = ConsoleTaskMonitor()

        for func in program.getFunctionManager().getFunctions(True):
            if func.getName() == target_func:
                results = decomp.decompileFunction(func, 60, monitor)
                if results.decompileCompleted():
                    output = {
                        "function": target_func,
                        "address": str(func.getEntryPoint()),
                        "c_code": results.getDecompiledFunction().getC(),
                    }
                    print(json.dumps(output, indent=2))
                    return
                print(json.dumps({"error": f"Decompilation failed for '{target_func}'"}))
                sys.exit(1)

    print(json.dumps({"error": f"Function '{target_func}' not found"}))
    sys.exit(1)


if __name__ == "__main__":
    main()
