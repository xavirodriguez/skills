#@category Decomp
"""Ghidra evidence collector for PH Tier 2 challenge candidates.

Usage:
  analyzeHeadless <project-dir> <project-name> -process <program> \
    -scriptPath <skills>/decomp/scripts \
    -postScript tier2_ghidra_scout.py <objdiff-report.json>
"""

import json
import math

from ghidra.program.model.block import BasicBlockModel


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def to_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 16)
            except ValueError:
                return None
    return None


def percentile75(values):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * 0.75
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def report_functions(report):
    rows = []
    for unit in report.get("units", []):
        if not isinstance(unit, dict):
            continue
        functions = unit.get("functions")
        if not isinstance(functions, list):
            continue
        for function in functions:
            if not isinstance(function, dict):
                continue
            fuzzy = function.get("fuzzy_match_percent", 0)
            match = float(fuzzy) if fuzzy is not None else 0.0
            size = to_int(function.get("size"))
            if size is None:
                continue
            rows.append({
                "name": str(function.get("name", "")),
                "address": function.get("address"),
                "size": size,
                "match_percent": match,
                "unit": unit.get("name"),
            })
    return rows


def resolve_function(query):
    fm = currentProgram.getFunctionManager()
    for function in fm.getFunctions(True):
        if function.getName() == query:
            return function

    try:
        address = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(query)
        function = fm.getFunctionContaining(address)
        if function is not None:
            return function
    except Exception:
        pass
    return None


def instructions(function):
    listing = currentProgram.getListing()
    iterator = listing.getInstructions(function.getBody(), True)
    result = []
    while iterator.hasNext():
        result.append(iterator.next())
    return result


def blocks(function):
    try:
        model = BasicBlockModel(currentProgram)
        iterator = model.getCodeBlocksContaining(function.getBody(), monitor)
        count = 0
        while iterator.hasNext():
            iterator.next()
            count += 1
        return count
    except Exception:
        return 0


def control_flow(function, insns):
    body = function.getBody()
    has_branch = False
    has_loop = False
    has_switch = False
    has_store = False

    for instruction in insns:
        flow = safe(lambda: instruction.getFlowType())
        if flow is not None:
            has_branch = has_branch or safe(lambda: flow.isJump(), False)
            has_switch = has_switch or safe(lambda: flow.isComputed(), False)

        for target in safe(lambda: instruction.getFlows(), []) or []:
            try:
                if body.contains(target) and target.getOffset() <= instruction.getAddress().getOffset():
                    has_loop = True
            except Exception:
                pass

        if len(safe(lambda: list(instruction.getFlows()), []) or []) > 1:
            has_switch = True

        for op in instruction.getPcode():
            if safe(lambda o=op: str(o.getMnemonic()).upper() == "STORE", False):
                has_store = True

    return {
        "has_branch": bool(has_branch),
        "has_loop": bool(has_loop),
        "has_switch": bool(has_switch),
        "has_store": bool(has_store),
    }


def global_count(function, insns):
    listing = currentProgram.getListing()
    seen = set()
    count = 0
    for instruction in insns:
        for ref in instruction.getReferencesFrom():
            target = ref.getToAddress()
            if target is None:
                continue
            data = safe(lambda t=target: listing.getDataAt(t))
            if data is None:
                continue
            key = str(target)
            if key not in seen:
                seen.add(key)
                count += 1
    return count


def evidence(function):
    insns = instructions(function)
    cf = control_flow(function, insns)
    callers = len(list(function.getCallingFunctions(monitor)))
    callees = len(list(function.getCalledFunctions(monitor)))

    return {
        "name": function.getName(),
        "entry": str(function.getEntryPoint()),
        "signature": safe(lambda: str(function.getSignature()), ""),
        "instructions": len(insns),
        "blocks": blocks(function),
        "callers": callers,
        "callees": callees,
        "globals": global_count(function, insns),
        "is_thunk": safe(lambda: function.isThunk(), False),
        "is_external": safe(lambda: function.isExternal(), False),
        **cf,
    }


def main():
    args = getScriptArgs()
    if not args:
        raise RuntimeError("Missing objdiff report path")

    with open(args[0], "r") as handle:
        report = json.load(handle)

    rows = report_functions(report)
    undecompiled = [
        row for row in rows
        if row["match_percent"] <= 0.0 and row["size"] > 0
    ]
    p75 = percentile75([row["size"] for row in undecompiled])
    threshold = max(256, p75) if p75 is not None else None

    candidates = []
    unresolved = []

    for row in undecompiled:
        if threshold is None or row["size"] < threshold:
            continue

        function = resolve_function(row["name"])
        if function is None and row.get("address") is not None:
            function = resolve_function(str(row["address"]))

        if function is None:
            unresolved.append({
                "name": row["name"],
                "address": row.get("address"),
                "size": row["size"],
            })
            continue

        ghidra = evidence(function)
        candidates.append({
            **row,
            "entry": ghidra["entry"],
            "instructions": ghidra["instructions"],
            "blocks": ghidra["blocks"],
            "callers": ghidra["callers"],
            "callees": ghidra["callees"],
            "globals": ghidra["globals"],
            "signature": ghidra["signature"],
            "has_branch": ghidra["has_branch"],
            "has_loop": ghidra["has_loop"],
            "has_switch": ghidra["has_switch"],
            "has_store": ghidra["has_store"],
            "is_thunk": ghidra["is_thunk"],
            "is_external": ghidra["is_external"],
            "ghidra_name": ghidra["name"],
        })

    print(json.dumps({
        "format": "ph-tier2-ghidra-v1",
        "summary": {
            "undecompiled_functions": len(undecompiled),
            "p75_bytes": p75,
            "threshold_bytes": threshold,
            "candidate_count": len(candidates),
            "unresolved_count": len(unresolved),
        },
        "candidates": candidates,
        "unresolved": unresolved,
        "note": "Evidence only. objdiff remains authoritative for match status.",
    }, indent=2, sort_keys=True))


main()
