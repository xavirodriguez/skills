#@category Decomp
"""Ghidra scout for functions that already satisfy the Tier 2 size gate."""

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
        try:
            return int(value.strip(), 0)
        except ValueError:
            try:
                return int(value.strip(), 16)
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
            size = to_int(function.get("size"))
            if size is None:
                continue
            fuzzy = function.get("fuzzy_match_percent", 0)
            try:
                match = float(fuzzy) if fuzzy is not None else 0.0
            except (TypeError, ValueError):
                match = 0.0
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
        return fm.getFunctionContaining(address)
    except Exception:
        return None


def instructions(function):
    iterator = currentProgram.getListing().getInstructions(function.getBody(), True)
    result = []
    while iterator.hasNext():
        result.append(iterator.next())
    return result


def block_count(function):
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
    conditional_branches = 0
    unconditional_branches = 0
    computed_jumps = 0
    back_edges = 0
    max_flow_targets = 0
    stores = 0

    for instruction in insns:
        flow = safe(lambda: instruction.getFlowType())
        if flow is not None:
            if safe(lambda: flow.isConditional(), False):
                conditional_branches += 1
            elif safe(lambda: flow.isJump(), False):
                unconditional_branches += 1
            if safe(lambda: flow.isComputed(), False):
                computed_jumps += 1

        flows = safe(lambda: list(instruction.getFlows()), []) or []
        max_flow_targets = max(max_flow_targets, len(flows))

        for target in flows:
            try:
                if body.contains(target) and target.getOffset() <= instruction.getAddress().getOffset():
                    back_edges += 1
            except Exception:
                pass

        for op in instruction.getPcode():
            if safe(lambda o=op: str(o.getMnemonic()).upper() == "STORE", False):
                stores += 1

    has_switch = computed_jumps > 0 or max_flow_targets > 2
    has_loop = back_edges > 0
    has_branch = conditional_branches > 0 or unconditional_branches > 0
    return {
        "conditional_branches": conditional_branches,
        "unconditional_branches": unconditional_branches,
        "computed_jumps": computed_jumps,
        "back_edges": back_edges,
        "max_flow_targets": max_flow_targets,
        "has_branch": has_branch,
        "has_loop": has_loop,
        "has_switch": has_switch,
        "stores": stores,
        "has_store": stores > 0,
    }


def global_count(function, insns):
    listing = currentProgram.getListing()
    seen = set()
    for instruction in insns:
        for ref in instruction.getReferencesFrom():
            target = ref.getToAddress()
            if target is None:
                continue
            data = safe(lambda t=target: listing.getDataAt(t))
            if data is not None:
                seen.add(str(target))
    return len(seen)


def evidence(function):
    insns = instructions(function)
    cf = control_flow(function, insns)
    return {
        "name": function.getName(),
        "entry": str(function.getEntryPoint()),
        "signature": safe(lambda: str(function.getSignature()), ""),
        "instructions": len(insns),
        "blocks": block_count(function),
        "callers": len(list(function.getCallingFunctions(monitor))),
        "callees": len(list(function.getCalledFunctions(monitor))),
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

        evidence_data = evidence(function)
        candidates.append({
            **row,
            "entry": evidence_data["entry"],
            "instructions": evidence_data["instructions"],
            "blocks": evidence_data["blocks"],
            "callers": evidence_data["callers"],
            "callees": evidence_data["callees"],
            "globals": evidence_data["globals"],
            "signature": evidence_data["signature"],
            "has_branch": evidence_data["has_branch"],
            "has_loop": evidence_data["has_loop"],
            "has_switch": evidence_data["has_switch"],
            "conditional_branches": evidence_data["conditional_branches"],
            "unconditional_branches": evidence_data["unconditional_branches"],
            "computed_jumps": evidence_data["computed_jumps"],
            "back_edges": evidence_data["back_edges"],
            "max_flow_targets": evidence_data["max_flow_targets"],
            "stores": evidence_data["stores"],
            "has_store": evidence_data["has_store"],
            "is_thunk": evidence_data["is_thunk"],
            "is_external": evidence_data["is_external"],
            "ghidra_name": evidence_data["name"],
        })

    print(json.dumps({
        "format": "ph-tier2-ghidra-v2",
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
