#@category Decomp
# Read-only Ghidra headless evidence collector.
#
# Usage:
#   analyzeHeadless <project-dir> <project-name> -process <program> \
#     -scriptPath decomp/scripts -postScript analyze_function.py <name-or-address>
#
# The script intentionally avoids mutating the Ghidra database.

import json
import sys

from ghidra.program.model.block import BasicBlockModel


def safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def address_text(address):
    return str(address) if address is not None else None


def resolve_function(program, query):
    fm = program.getFunctionManager()

    if query:
        for fn in fm.getFunctions(True):
            if fn.getName() == query:
                return fn

        try:
            address = program.getAddressFactory().getDefaultAddressSpace().getAddress(query)
            fn = fm.getFunctionContaining(address)
            if fn is not None:
                return fn
        except Exception:
            pass

    current = getFunctionContaining(currentAddress)
    if current is not None:
        return current

    raise RuntimeError("Function not found: %s" % query)


def collect_signature(function):
    return {
        "name": function.getName(),
        "entry": address_text(function.getEntryPoint()),
        "signature": safe(lambda: str(function.getSignature())),
        "calling_convention": safe(lambda: function.getCallingConventionName()),
        "return_type": safe(lambda: str(function.getReturnType())),
        "parameters": [
            {
                "name": safe(lambda p=p: p.getName()),
                "type": safe(lambda p=p: str(p.getDataType())),
                "ordinal": safe(lambda p=p: p.getOrdinal()),
                "storage": safe(lambda p=p: str(p.getVariableStorage())),
            }
            for p in function.getParameters()
        ],
    }


def collect_instructions(program, function):
    listing = program.getListing()
    body = function.getBody()
    instructions = []
    iterator = listing.getInstructions(body, True)

    while iterator.hasNext():
        ins = iterator.next()
        pcode = []
        for op in ins.getPcode():
            inputs = []
            for varnode in op.getInputs():
                inputs.append({
                    "space": safe(lambda v=varnode: v.getAddress().getAddressSpace().getName()),
                    "offset": safe(lambda v=varnode: "0x%x" % v.getOffset()),
                    "size": safe(lambda v=varnode: v.getSize()),
                    "text": safe(lambda v=varnode: str(v)),
                })
            output = op.getOutput()
            pcode.append({
                "op": op.getMnemonic(),
                "output": safe(lambda: str(output)) if output is not None else None,
                "inputs": inputs,
            })

        refs = []
        for ref in ins.getReferencesFrom():
            refs.append({
                "from": address_text(ref.getFromAddress()),
                "to": address_text(ref.getToAddress()),
                "type": safe(lambda r=ref: str(r.getReferenceType())),
                "primary": safe(lambda r=ref: r.isPrimary()),
            })

        instructions.append({
            "address": address_text(ins.getAddress()),
            "text": str(ins),
            "mnemonic": safe(lambda: ins.getMnemonicString()),
            "length": safe(lambda: ins.getLength()),
            "pcode": pcode,
            "references": refs,
        })

    return instructions


def collect_cfg(program, function):
    blocks = []
    model = BasicBlockModel(program)
    iterator = model.getCodeBlocksContaining(function.getBody(), monitor)

    while iterator.hasNext():
        block = iterator.next()
        destinations = []
        dests = block.getDestinations(monitor)
        while dests.hasNext():
            ref = dests.next()
            destinations.append({
                "address": address_text(ref.getDestinationAddress()),
                "flow": safe(lambda r=ref: str(r.getFlowType())),
            })

        blocks.append({
            "start": address_text(block.getFirstStartAddress()),
            "end": address_text(block.getMinAddress()),
            "max": address_text(block.getMaxAddress()),
            "destinations": destinations,
        })

    return blocks


def collect_relationships(program, function):
    callers = []
    for caller in function.getCallingFunctions(monitor):
        callers.append({
            "name": caller.getName(),
            "entry": address_text(caller.getEntryPoint()),
        })

    callees = []
    for callee in function.getCalledFunctions(monitor):
        callees.append({
            "name": callee.getName(),
            "entry": address_text(callee.getEntryPoint()),
        })

    return {"callers": callers, "callees": callees}


def collect_memory(program, function):
    listing = program.getListing()
    body = function.getBody()
    accesses = []
    data_refs = {}

    iterator = listing.getInstructions(body, True)
    while iterator.hasNext():
        ins = iterator.next()
        for ref in ins.getReferencesFrom():
            target = ref.getToAddress()
            if target is None:
                continue
            data = safe(lambda t=target: listing.getDataAt(t))
            if data is not None:
                key = address_text(target)
                data_refs[key] = {
                    "type": safe(lambda d=data: str(d.getDataType())),
                    "value": safe(lambda d=data: str(d.getValue())),
                    "length": safe(lambda d=data: d.getLength()),
                    "label": safe(lambda d=data: d.getLabel()),
                }

        text = str(ins).lower()
        if any(token in text for token in ["sp", "fp"]):
            accesses.append({
                "address": address_text(ins.getAddress()),
                "instruction": str(ins),
            })

    return {"stack_like_instructions": accesses, "data": data_refs}


def main():
    args = getScriptArgs()
    query = args[0] if len(args) > 0 else None
    function = resolve_function(currentProgram, query)

    result = {
        "program": currentProgram.getName(),
        "language": safe(lambda: str(currentProgram.getLanguageID())),
        "compiler_spec": safe(lambda: str(currentProgram.getCompilerSpec().getCompilerSpecID())),
        "function": collect_signature(function),
        "instructions": collect_instructions(currentProgram, function),
        "cfg": collect_cfg(currentProgram, function),
        "relationships": collect_relationships(currentProgram, function),
        "memory": collect_memory(currentProgram, function),
    }

    print(json.dumps(result, indent=2, sort_keys=True))


main()
