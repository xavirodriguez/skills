import sys
import pyghidra

def run_pcode_analysis(binary_path: str):
    # 1. Inicializar PyGhidra
    pyghidra.start()
    
    # Importaciones de las clases Java de Ghidra tras inicializar el motor JNI
    from ghidra.app.decompiler import DecompInterface
    from ghidra.program.model.data import (
        IntegerDataType, CharDataType, PointerDataType, ParameterImpl
    )
    from ghidra.program.model.symbol import SourceType
    from ghidra.program.model.pcode import PcodeOp
    from ghidra.program.model.listing import Function
    from ghidra.util.task import ConsoleTaskMonitor

    with pyghidra.open_program(binary_path) as flat_api:
        program = flat_api.getCurrentProgram()
        monitor = ConsoleTaskMonitor()
        
        # -------------------------------------------------------------
        # PASO 1: Localizar la función main
        # -------------------------------------------------------------
        symbol_table = program.getSymbolTable()
        main_symbols = list(symbol_table.getSymbols("main"))
        
        if not main_symbols:
            print("[-] No se encontró el símbolo 'main' en la tabla de símbolos.")
            return

        main_func = flat_api.getFunctionAt(main_symbols[0].getAddress())
        print(f"[+] 'main' localizada en la dirección: {main_func.getEntryPoint()}")

        # -------------------------------------------------------------
        # PASO 2: Corregir la firma de la función main (ABI Standard)
        # -------------------------------------------------------------
        dtm = program.getDataTypeManager()
        int_dt = IntegerDataType.dataType
        char_dt = CharDataType.dataType
        char_ptr_ptr_dt = PointerDataType(PointerDataType(char_dt))

        # Crear nuevos parámetros: argc y argv
        param_argc = ParameterImpl("argc", int_dt, program)
        param_argv = ParameterImpl("argv", char_ptr_ptr_dt, program)

        # Actualizar tipo de retorno y parámetros en la base de datos de Ghidra
        main_func.setReturnType(int_dt, SourceType.USER_DEFINED)
        main_func.updateFunction(
            None, # Mantiene la convención de llamada por defecto
            None,
            Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL,
            True,
            SourceType.USER_DEFINED,
            [param_argc, param_argv]
        )
        print("[+] Firma de 'main' actualizada a: int main(int argc, char **argv)")

        # -------------------------------------------------------------
        # PASO 3: Descompilar a P-code y aplicar Renombrado Semántico
        # -------------------------------------------------------------
        decomp = DecompInterface()
        decomp.openProgram(program)
        results = decomp.decompileFunction(main_func, 60, monitor)

        if not results.decompileCompleted():
            print("[-] Error al descompilar la función main.")
            return

        high_func = results.getHighFunction()
        pcode_ops = high_func.getPcodeOps()

        renamed_count = 0

        for op in pcode_ops:
            opcode = op.getOpcode()

            # Analizar llamadas a funciones (CALL P-code)
            if opcode == PcodeOp.CALL:
                target_addr = op.getInput(0).getAddress()
                called_func = program.getFunctionManager().getFunctionAt(target_addr)

                if called_func:
                    func_name = called_func.getName()

                    # HEURÍSTICA A: Argumentos de funciones de texto (puts, strlen, printf)
                    if func_name in ["puts", "strlen", "printf", "strcpy"]:
                        if op.getNumInputs() > 1:
                            # Entrada 0 es la dirección de destino; Entrada 1 es el primer argumento
                            arg1_node = op.getInput(1)
                            high_var = arg1_node.getHigh()

                            if high_var and high_var.getSymbol():
                                symbol = high_var.getSymbol()
                                curr_name = symbol.getName()
                                # Renombrar solo si conserva el nombre genérico predeterminado
                                if curr_name.startswith("uVar") or curr_name.startswith("local_"):
                                    symbol.setName("str_input", SourceType.USER_DEFINED)
                                    print(f"    [*] Variable '{curr_name}' renombra a 'str_input' (pasada a {func_name})")
                                    renamed_count += 1

                    # HEURÍSTICA B: Valor de retorno de strlen
                    if func_name == "strlen":
                        out_node = op.getOutput()
                        if out_node and out_node.getHigh():
                            symbol = out_node.getHigh().getSymbol()
                            if symbol:
                                curr_name = symbol.getName()
                                if curr_name.startswith("uVar") or curr_name.startswith("iVar"):
                                    symbol.setName("str_len", SourceType.USER_DEFINED)
                                    print(f"    [*] Variable '{curr_name}' renombra a 'str_len' (retorno de strlen)")
                                    renamed_count += 1

            # HEURÍSTICA C: Comparaciones en bucles o condiciones (INT_EQUAL / INT_NOTEQUAL)
            elif opcode in [PcodeOp.INT_EQUAL, PcodeOp.INT_NOTEQUAL]:
                # Verificar si uno de los operandos es una constante 0 o fin de cadena '\0'
                for i in range(1, op.getNumInputs()):
                    input_node = op.getInput(i)
                    if input_node.isConstant() and input_node.getOffset() == 0:
                        other_node = op.getInput(2 if i == 1 else 1)
                        if other_node.getHigh() and other_node.getHigh().getSymbol():
                            symbol = other_node.getHigh().getSymbol()
                            curr_name = symbol.getName()
                            if curr_name.startswith("uVar") or curr_name.startswith("cVar"):
                                symbol.setName("char_curr", SourceType.USER_DEFINED)
                                print(f"    [*] Variable '{curr_name}' renombra a 'char_curr' (comparada con null byte)")
                                renamed_count += 1

        print(f"[+] Análisis de P-code finalizado. Total de variables renombradas: {renamed_count}")

        # -------------------------------------------------------------
        # PASO 4: Exportar el código C limpio resultante
        # -------------------------------------------------------------
        # Volver a descompilar para reflejar las firmas y variables renombradas
        clean_results = decomp.decompileFunction(main_func, 60, monitor)
        print("\n--- CÓDIGO C DESCOMPILADO Y RESTRUCTURADO ---")
        print(clean_results.getDecompiledFunction().getC())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python fix_main_pcode.py <path_al_binario>")
        sys.exit(1)

    run_pcode_analysis(sys.argv[1])