#@category Decomp
# Read-only Ghidra function scout.
#
# Ranks likely first-match targets using evidence available in Ghidra.
# Optional JSON metadata can add authoritative project information:
#
# {
#   "nonmatching": ["0x08000100", "functionName"],
#   "matching": ["0x08000200", "otherFunction"],
#   "matching_ranges": [["0x08001000", "0x08001080"]]
# }
#
# Usage:
#   ... -postScript scout_functions.py
#   ... -postScript scout_functions.py scout.json
#
# Without metadata, nonmatching/matching status is deliberately reported as
# "unknown". A scout score never substitutes for the project's authoritative
# objdiff/compare result.

import json
import re

from ghidra.program.model.block import BasicBlockModel
from ghidra.program.model.data import Structure


GENERIC_PREFIXES = ("FUN_", "thunk_", "LAB_", "sub_")
PROBLEMATIC_MNEMONICS = (
    "div", "idiv", "udiv", "sdiv", "msub",
    "sqrt", "fsqrt",
)
PROBLEMATIC_TEXT = (
    "jumptable",
    "indirect",
    "switch",
)


def safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def load_metadata():
    args = getScriptArgs()
    if not args:
        return {}
    try:
        with open(args[0], "r") as handle:
            return json.load(handle)
    except Exception:
        return {}


def address_matches(function, values):
    entry = str(function.getEntryPoint()).lower()
    name = function.getName()
    return name in values or entry in {str(v).lower() for v in values}


def status_for(function, metadata):
    if address_matches(function, metadata.get("nonmatching", [])):
        return "nonmatching"
    if address_matches(function, metadata.get("matching", [])):
        return "matching"

    for start, end in metadata.get("matching_ranges", []):
        if str(start).lower() <= str(function.getEntryPoint()).lower() <= str(end).lower():
            return "matching"

    # Ghidra comments/names are useful local hints, but not authoritative.
    text = (function.getName() + " " + safe(lambda: function.getComment(), "")).lower()
    if "nonmatching" in text or "non-matching" in text:
        return "nonmatching"
    if "matching" in text and "nonmatching" not in text:
        return "matching"

    return "unknown"


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


def collect_instructions(program, function):
    return list(program.getListing().getInstructions(function.getBody(), True))


def count_globals(program, function):
    listing = program.getListing()
    count = 0
    seen = set()

    for instruction in collect_instructions(program, function):
        for ref in instruction.getReferencesFrom():
            target = ref.getToAddress()
            if target is None:
                continue
            data = safe(lambda t=target: listing.getDataAt(t))
            if data is None:
                continue
            key = str(target)
            if key in seen:
                continue
            seen.add(key)
            count += 1

    return count


def defined_structs(function):
    types = []
    for parameter in function.getParameters():
        data_type = parameter.getDataType()
        if isinstance(data_type, Structure):
            types.append(str(data_type.getName()))

    for variable in function.getLocalVariables():
        data_type = variable.getDataType()
        if isinstance(data_type, Structure):
            types.append(str(data_type.getName()))

    return sorted(set(types))


def complexity_flags(program, function):
    flags = set()

    for instruction in collect_instructions(program, function):
        mnemonic = safe(lambda i=instruction: i.getMnemonicString(), "").lower()
        text = str(instruction).lower()

        if any(token in mnemonic for token in PROBLEMATIC_MNEMONICS):
            flags.add("expensive_or_unusual_arithmetic")
        if any(token in text for token in PROBLEMATIC_TEXT):
            flags.add("indirect_or_switch_control_flow")

        for ref in instruction.getReferencesFrom():
            if safe(lambda r=ref: r.getReferenceType().isComputed(), False):
                flags.add("computed_reference")

    if len(list(function.getCalledFunctions(monitor))) > 8:
        flags.add("many_callees")

    return sorted(flags)


def neighboring_functions(program, function):
    fm = program.getFunctionManager()
    all_functions = list(fm.getFunctions(True))
    all_functions.sort(key=lambda item: item.getEntryPoint().getOffset())
    try:
        index = all_functions.index(function)
    except ValueError:
        return []

    neighbours = []
    for other in all_functions[max(0, index - 2):index + 3]:
        if other == function:
            continue
        neighbours.append({
            "name": other.getName(),
            "entry": str(other.getEntryPoint()),
        })
    return neighbours


def neighbor_matching_evidence(program, function, metadata):
    neighbors = neighboring_functions(program, function)
    known_matching = []
    matching = metadata.get("matching", [])
    ranges = metadata.get("matching_ranges", [])

    for neighbor in neighbors:
        entry = neighbor["entry"].lower()
        name = neighbor["name"]
        if name in matching or entry in {str(v).lower() for v in matching}:
            known_matching.append(neighbor)
            continue
        for start, end in ranges:
            if str(start).lower() <= entry <= str(end).lower():
                known_matching.append(neighbor)
                break

    return known_matching


def score_function(program, function, metadata):
    name = function.getName()
    size = instruction_count(program, function)
    blocks = block_count(program, function)
    params = len(function.getParameters())
    callers = len(list(function.getCallingFunctions(monitor)))
    callees = len(list(function.getCalledFunctions(monitor)))
    globals_count = count_globals(program, function)
    structs = defined_structs(function)
    flags = complexity_flags(program, function)
    status = status_for(function, metadata)
    known_matching_neighbors = neighbor_matching_evidence(program, function, metadata)

    score = 35.0
    reasons = []
    penalties = []

    # Highest-value signal: authoritative/project-provided nonmatching status.
    if status == "nonmatching":
        score += 35
        reasons.append("known nonmatching")
    elif status == "matching":
        score -= 50
        penalties.append("known matching")
    else:
        reasons.append("match status unknown")

    if 8 <= size <= 80:
        score += 18
        reasons.append("few instructions")
    elif 81 <= size <= 140:
        score += 8
        reasons.append("moderate instruction count")
    elif size < 8:
        score -= 25
        penalties.append("trivial/stub")
    else:
        penalty = min(25, (size - 140) / 10.0)
        score -= penalty
        penalties.append("large function")

    if blocks <= 4:
        score += 14
        reasons.append("very simple CFG")
    elif blocks <= 6:
        score += 10
        reasons.append("simple CFG")
    elif blocks <= 12:
        score += 3
    else:
        score -= min(15, blocks - 12)
        penalties.append("complex CFG")

    # A resolved signature is much easier to reconstruct than a guessed one.
    signature = safe(lambda: str(function.getSignature()), "")
    if signature and "undefined" not in signature.lower():
        score += 10
        reasons.append("known/resolved signature")
    else:
        score -= 8
        penalties.append("uncertain signature")

    if globals_count == 0:
        score += 10
        reasons.append("no global data references")
    elif globals_count <= 2:
        score += 5
        reasons.append("few globals")
    elif globals_count > 8:
        score -= 8
        penalties.append("many globals")

    if known_matching_neighbors:
        score += min(12, len(known_matching_neighbors) * 6)
        reasons.append("nearby matching functions")

    if structs:
        score += min(10, len(structs) * 5)
        reasons.append("existing structs/types")
    else:
        reasons.append("no local struct evidence")

    if not flags:
        score += 10
        reasons.append("no known problematic constructs")
    else:
        score -= min(20, len(flags) * 6)
        penalties.extend(flags)

    if params <= 4:
        score += 5
        reasons.append("manageable parameter count")
    else:
        score -= min(10, params - 4)
        penalties.append("many parameters")

    if 0 < callees <= 4:
        score += 4
        reasons.append("few callees")
    elif callees > 8:
        score -= 6
        penalties.append("many callees")

    if callers > 0:
        score += 3
        reasons.append("has caller context")

    if name.startswith(GENERIC_PREFIXES):
        score -= 6
        penalties.append("generic/auto-generated name")
    else:
        score += 4
        reasons.append("named function")

    if function.isThunk():
        score -= 25
        penalties.append("thunk")

    if function.isExternal():
        score -= 50
        penalties.append("external")

    return {
        "score": round(score, 2),
        "status": status,
        "name": name,
        "entry": str(function.getEntryPoint()),
        "instructions": size,
        "blocks": blocks,
        "parameters": params,
        "callees": callees,
        "callers": callers,
        "globals": globals_count,
        "defined_structs": structs,
        "problematic_constructs": flags,
        "nearby_matching": known_matching_neighbors,
        "reasons": reasons,
        "penalties": penalties,
        "signature": signature,
    }


def main():
    metadata = load_metadata()
    results = []
    fm = currentProgram.getFunctionManager()

    for function in fm.getFunctions(True):
        if function.isExternal():
            continue
        try:
            results.append(score_function(currentProgram, function, metadata))
        except Exception:
            # One malformed function should not prevent scouting the rest.
            pass

    results.sort(key=lambda item: (-item["score"], item["instructions"], item["entry"]))

    print(json.dumps({
        "program": currentProgram.getName(),
        "language": safe(lambda: str(currentProgram.getLanguageID())),
        "compiler_spec": safe(lambda: str(currentProgram.getCompilerSpec().getCompilerSpecID())),
        "metadata_loaded": bool(metadata),
        "candidates": results[:100],
        "note": "Ranking only. Verify status and exact match with the project's authoritative comparison tool.",
    }, indent=2, sort_keys=True))


main()
