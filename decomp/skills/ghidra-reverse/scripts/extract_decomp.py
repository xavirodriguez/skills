import sys
import json
import pyghidra

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Uso: extract_decomp.py <binary_path> <function_name>"}))
        sys.exit(1)

    binary_path = sys.argv[1]
    target_func = sys.argv[2]

    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor

    with pyghidra.open_program(binary_path) as flat_api:
        program = flat_api.getCurrentProgram()
        decomp = DecompInterface()
        decomp.openProgram(program)
        monitor = ConsoleTaskMonitor()
        
        functions = program.getFunctionManager().getFunctions(True)
        for func in functions:
            if func.getName() == target_func:
                results = decomp.decompileFunction(func, 60, monitor)
                if results.decompileCompleted():
                    output = {
                        "function": target_func,
                        "address": func.getEntryPoint().toString(),
                        "c_code": results.getDecompiledFunction().getC()
                    }
                    print(json.dumps(output, indent=2))
                    return

    print(json.dumps({"error": f"Función '{target_func}' no encontrada"}))

if __name__ == "__main__":
    main()