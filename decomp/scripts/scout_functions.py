#@category Decomp
# Read-only Ghidra function scout.
#
# Produces a ranked list of functions that are usually practical first
# matching targets. It deliberately does not pretend to know match status:
# exact match status must come from the project's authoritative diff tool.

import json

from ghidra.program.model.block import BasicBlockModel


def safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def instruction_count(program, function):
    return sum(1 for _ in program.getListing().getInstructions(function.getBody(), True))


def block_count(program, function):
    try:
        model = BasicBlockModel(program)
        iterator = model.getCodeBlocksContaining(function.getBody(), monitor)
        return sum(1 for _ in iter_blocks(iterator))
    except Exception:
        return 0


def iter_blocks(iterator):
    while iterator.hasNext():
        yield iterator.next()


def score_function(program, function):
    name = function.getName()
    size = instruction_count(program, function)
    blocks = block_count(program, function)
    params = len(function.getParameters())
    callers = len(list(function.getCallingFunctions(monitor)))
    callees = len(list(function.getCalledFunctions(monitor)))

    score = 50.0
    reasons = []

    # Small enough to understand and iterate quickly, but ignore trivial stubs.
    if 8 <= size <= 80:
        score += 20
        reasons.append("small-medium instruction count")
    elif 81 <= size <= 140:
        score += 8
        reasons.append("moderate instruction count")
    elif size < 8:
        score -= 30
        reasons.append("likely stub/trivial")
    else:
        score -= min(25, (size - 140) / 10.0)
        reasons.append("large function")

    if blocks <= 6:
        score += 12
        reasons.append("simple CFG")
    elif blocks <= 12:
        score += 5
    else:
        score -= min(15, blocks - 12)

    if params <= 4:
        score += 6
        reasons.append("manageable parameter count")
    else:
        score -= min(10, params - 4)

    if 0 < callees <= 4:
        score += 5
        reasons.append("few callees")
    elif callees > 8:
        score -= 6

    if callers > 0:
        score += 4
        reasons.append("has caller context")

    if name.startswith(("FUN_", "thunk_", "LAB_")):
        score -= 10
        reasons.append("generic/auto-generated name")
    else:
        score += 5
        reasons.append("named function")

    if function.isThunk():
        score -= 25
        reasons.append("thunk")

    if function.isExternal():
        score -= 50
        reasons.append("external")

    return {
        "score": round(score, 2),
        "name": name,
        "entry": str(function.getEntryPoint()),
        "instructions": size,
        "blocks": blocks,
        "parameters": params,
        "callers": callers,
        "callees": callees,
        "reasons": reasons,
    }


def main():
    results = []
    fm = currentProgram.getFunctionManager()

    for function in fm.getFunctions(True):
        if function.isExternal():
            continue
        try:
            results.append(score_function(currentProgram, function))
        except Exception:
            # One malformed function should not prevent scouting the rest.
            pass

    results.sort(key=lambda item: (-item["score"], item["instructions"], item["entry"]))

    print(json.dumps({
        "program": currentProgram.getName(),
        "language": safe(lambda: str(currentProgram.getLanguageID())),
        "compiler_spec": safe(lambda: str(currentProgram.getCompilerSpec().getCompilerSpecID())),
        "candidates": results[:100],
        "note": "Candidate ranking only; verify match status with the project's authoritative diff.",
    }, indent=2, sort_keys=True))


main()
