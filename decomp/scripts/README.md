# Ghidra matching helpers

These scripts are intentionally read-only: they turn Ghidra's analysis into structured evidence for a matching-decomp workflow.

## `analyze_function.py`

Run from Ghidra headless mode after importing/opening the target program:

```text
analyzeHeadless <project-dir> <project-name> -process <program> \
  -scriptPath decomp/scripts -postScript analyze_function.py <function-or-address>
```

The script emits one JSON document to stdout containing the function signature, assembly, P-code, CFG edges, callers/callees, Xrefs, strings, stack accesses, and referenced data.

## `scout_functions.py`

Run the same way without a target argument. It ranks functions that are good candidates for a first matching contribution. The score deliberately favours small, self-contained functions with useful symbols/types and nearby matching context rather than merely selecting the shortest function.

Both scripts are evidence collectors. They do not edit source code or claim a match.

## Function scouting signals

`scout_functions.py` combines these signals:

- known `nonmatching` status when supplied by project metadata or a local Ghidra annotation;
- low instruction count;
- resolved function signature;
- few references to global/data objects;
- simple CFG;
- neighbouring functions known to match;
- parameters/locals using already-defined structures;
- absence of constructs that often make matching harder, such as computed control flow or unusual arithmetic;
- manageable parameter/callee counts and useful caller context.

For authoritative project status, pass a small JSON metadata file as the first script argument:

```json
{
  "nonmatching": ["0x08000100", "function_name"],
  "matching": ["0x08000200"],
  "matching_ranges": [["0x08001000", "0x08001080"]]
}
```

This keeps the scout useful across different decompilation projects without hard-coding one project's symbol conventions.
