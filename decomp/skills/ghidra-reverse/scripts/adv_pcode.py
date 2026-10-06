import sys
import pyghidra

def run_extended_pcode_analysis(binary_path: str):
    pyghidra.start()
    
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
        # PASO 1: Localizar función main y corregir firma ABI
        # -------------------------------------------------------------
        symbol_table = program.getSymbolTable()
        main_symbols = list(symbol_table.getSymbols("main"))
        
        if not main_symbols:
            print("[-] Símbolo 'main' no encontrado.")
            return

        main_func = flat_api.getFunctionAt(main_symbols[0].getAddress())
        
        int_dt = IntegerDataType.dataType
        char_ptr_ptr_dt = PointerDataType(PointerDataType(CharDataType.dataType))

        main_func.setReturnType(int_dt, SourceType.USER_DEFINED)
        main_func.updateFunction(
            None, None,
            Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL,
            True, SourceType.USER_DEFINED,
            [ParameterImpl("argc", int_dt, program), ParameterImpl("argv", char_ptr_ptr_dt, program)]
        )
        print("[+] Firma de 'main' ajustada: int main(int argc, char **argv)")

        # -------------------------------------------------------------
        # PASO 2: Descompilación a P-code y Heurísticas Extendidas
        # -------------------------------------------------------------
        decomp = DecompInterface()
        decomp.openProgram(program)
        results = decomp.decompileFunction(main_func, 60, monitor)

        if not results.decompileCompleted():
            print("[-] Error al descompilar.")
            return

        high_func = results.getHighFunction()
        pcode_ops = high_func.getPcodeOps()

        renamed_count = 0

        # Prefijos predeterminados de Ghidra a reemplazar
        GENERIC_PREFIXES = ("uVar", "iVar", "pvVar", "local_", "cVar", "puVar", "pVar")

        def try_rename(varnode, new_name: str, reason: str) -> bool:
            nonlocal renamed_count
            if varnode and varnode.getHigh() and varnode.getHigh().getSymbol():
                symbol = varnode.getHigh().getSymbol()
                curr_name = symbol.getName()
                if any(curr_name.startswith(prefix) for prefix in GENERIC_PREFIXES):
                    symbol.setName(new_name, SourceType.USER_DEFINED)
                    print(f"    [*] Variable '{curr_name}' -> '{new_name}' ({reason})")
                    renamed_count += 1
                    return True
            return False

        for op in pcode_ops:
            opcode = op.getOpcode()

            # ---------------------------------------------------------
            # HEURÍSTICA 1: LLAMADAS A FUNCIONES (CALL)
            # ---------------------------------------------------------
            if opcode == PcodeOp.CALL:
                target_addr = op.getInput(0).getAddress()
                called_func = program.getFunctionManager().getFunctionAt(target_addr)

                if called_func:
                    func_name = called_func.getName()

                    # A. Cadenas de Texto (puts, strlen, printf, strcmp)
                    if func_name in ["puts", "strlen", "printf", "strcpy", "strcmp"]:
                        if op.getNumInputs() > 1:
                            try_rename(op.getInput(1), "str_input", f"arg1 de {func_name}")
                    if func_name == "strlen":
                        try_rename(op.getOutput(), "str_len", "retorno de strlen")

                    # B. Descriptores de Archivo POSIX (open, socket, read, write, close)
                    if func_name in ["open", "socket", "fileno", "accept"]:
                        try_rename(op.getOutput(), "file_fd", f"retorno de {func_name}")

                    if func_name in ["read", "write", "close"]:
                        if op.getNumInputs() > 1:
                            try_rename(op.getInput(1), "file_fd", f"fd arg1 de {func_name}")

                    # C. Flujos de Archivo ANSI C (fopen, fread, fwrite, fclose)
                    if func_name == "fopen":
                        try_rename(op.getOutput(), "file_ptr", "retorno de fopen")

                    if func_name == "fclose" and op.getNumInputs() > 1:
                        try_rename(op.getInput(1), "file_ptr", "stream arg de fclose")

                    if func_name in ["fread", "fwrite"] and op.getNumInputs() > 4:
                        # En fread(ptr, size, nmemb, stream), el stream es el 4to argumento (Input 4)
                        try_rename(op.getInput(4), "file_ptr", f"stream arg de {func_name}")

                    # D. Asignación Dinámica de Memoria Heap (malloc, calloc, realloc)
                    if func_name in ["malloc", "calloc", "realloc"]:
                        try_rename(op.getOutput(), "heap_buf", f"retorno de {func_name}")

            # ---------------------------------------------------------
            # HEURÍSTICA 2: ACCESO A CAMPOS DE ESTRUCTURA (PTRSUB / PTRADD)
            # ---------------------------------------------------------
            # PTRSUB calcula la dirección de un miembro dentro de un struct (base_ptr + offset)
            elif opcode == PcodeOp.PTRSUB:
                base_ptr_node = op.getInput(0)
                offset_node = op.getInput(1)

                # Si el offset no es 0, indica acceso a un miembro interno de la estructura
                if offset_node.isConstant() and offset_node.getOffset() > 0:
                    try_rename(base_ptr_node, "struct_ptr", "acceso a campo struct vía PTRSUB")

            # PTRADD se utiliza cuando se accede a un elemento de array dentro de una estructura
            elif opcode == PcodeOp.PTRADD:
                base_ptr_node = op.getInput(0)
                try_rename(base_ptr_node, "struct_arr_ptr", "indexación de estructura vía PTRADD")

            # ---------------------------------------------------------
            # HEURÍSTICA 3: COMPARACIÓN CONTRA NULL / BYTE CERO
            # ---------------------------------------------------------
            elif opcode in [PcodeOp.INT_EQUAL, PcodeOp.INT_NOTEQUAL]:
                for i in range(1, op.getNumInputs()):
                    input_node = op.getInput(i)
                    if input_node.isConstant() and input_node.getOffset() == 0:
                        other_node = op.getInput(2 if i == 1 else 1)
                        try_rename(other_node, "char_curr", "comparación contra byte nulo")

        print(f"[+] Total de variables renombradas mediante P-code: {renamed_count}")

        # -------------------------------------------------------------
        # PASO 3: Exportar el C resultante
        # -------------------------------------------------------------
        clean_results = decomp.decompileFunction(main_func, 60, monitor)
        print("\n--- CÓDIGO C CON HEURÍSTICAS DE ARCHIVOS Y ESTRUCTURAS ---")
        print(clean_results.getDecompiledFunction().getC())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python fix_main_pcode.py <path_al_binario>")
        sys.exit(1)

    run_extended_pcode_analysis(sys.argv[1])