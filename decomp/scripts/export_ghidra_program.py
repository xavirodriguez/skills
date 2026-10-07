#@category Decomp
# Read-only Ghidra headless exporter.
#
# Usage:
#   analyzeHeadless <project-dir> <project-name> -process <program> \
#     -scriptPath decomp/scripts -postScript export_ghidra_program.py
#
# The script exports program-level function, symbol and memory evidence as JSON
# and intentionally does not mutate the Ghidra database.

import json



def safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def address_text(address):
    return str(address) if address is not None else None


def collect_program():
    program = currentProgram
    address_factory = program.getAddressFactory()
    default_space = address_factory.getDefaultAddressSpace()

    return {
        "name": program.getName(),
        "language": safe(lambda: str(program.getLanguageID())),
        "compiler_spec": safe(lambda: str(program.getCompilerSpec().getCompilerSpecID())),
        "executable_format": safe(lambda: program.getExecutableFormat()),
        "image_base": address_text(program.getImageBase()),
        "default_address_space": safe(lambda: default_space.getName()),
        "min_address": address_text(program.getMinAddress()),
        "max_address": address_text(program.getMaxAddress()),
    }


def collect_functions():
    function_manager = currentProgram.getFunctionManager()
    result = []

    for function in function_manager.getFunctions(True):
        body = function.getBody()
        result.append({
            "name": function.getName(),
            "entry": address_text(function.getEntryPoint()),
            "body_min": address_text(body.getMinAddress()),
            "body_max": address_text(body.getMaxAddress()),
            "calling_convention": safe(lambda f=function: f.getCallingConventionName()),
            "signature": safe(lambda f=function: str(f.getSignature())),
            "source_type": safe(lambda f=function: str(f.getSymbol().getSource())),
            "is_thunk": safe(lambda f=function: f.isThunk(), False),
            "is_external": safe(lambda f=function: f.isExternal(), False),
        })

    return result


def collect_symbols():
    symbol_table = currentProgram.getSymbolTable()
    result = []

    for symbol in symbol_table.getAllSymbols(True):
        address = symbol.getAddress()
        if address is None or address.getAddressSpace() != currentProgram.getAddressFactory().getDefaultAddressSpace():
            continue

        source = safe(lambda s=symbol: str(s.getSource()), None)
        result.append({
            "name": symbol.getName(),
            "address": address_text(address),
            "symbol_type": safe(lambda s=symbol: str(s.getSymbolType())),
            "is_primary": safe(lambda s=symbol: s.isPrimary(), False),
            "source_type": source,
            "is_dynamic": safe(lambda s=symbol: s.isDynamic(), False),
            "is_external": safe(lambda s=symbol: s.isExternal(), False),
        })

    return result


def collect_memory_blocks():
    memory = currentProgram.getMemory()
    result = []

    for block in memory.getBlocks():
        result.append({
            "name": block.getName(),
            "start": address_text(block.getStart()),
            "end": address_text(block.getEnd()),
            "size": safe(lambda b=block: b.getSize(), None),
            "initialized": safe(lambda b=block: b.isInitialized(), None),
            "read": safe(lambda b=block: b.isRead(), None),
            "write": safe(lambda b=block: b.isWrite(), None),
            "execute": safe(lambda b=block: b.isExecute(), None),
            "volatile": safe(lambda b=block: b.isVolatile(), None),
            "overlay": safe(lambda b=block: b.isOverlay(), None),
        })

    return result


def main():
    result = {
        "format": "ghidra-program-evidence-v1",
        "program": collect_program(),
        "statistics": {},
        "functions": collect_functions(),
        "symbols": collect_symbols(),
        "memory_blocks": collect_memory_blocks(),
    }

    result["statistics"] = {
        "functions": len(result["functions"]),
        "symbols": len(result["symbols"]),
        "memory_blocks": len(result["memory_blocks"]),
    }

    print(json.dumps(result, indent=2, sort_keys=True))


main()
