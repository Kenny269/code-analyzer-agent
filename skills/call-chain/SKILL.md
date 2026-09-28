---
name: call-chain
description: Analyze call chains for a given symbol. Find what calls a function and what it calls. Use when the user asks about callers, callees, call chains, dependencies of a function, or who calls a specific function.
---

# Call Chain Analysis

## Steps

1. Extract the target symbol name from the user request.
2. Query CodeGraph for callers using `codegraph callers <symbol>`.
3. Query CodeGraph for callees using `codegraph callees <symbol>`.
4. Format the results as a call chain tree.

## Output Format

Return JSON with:
- `target`: the symbol name
- `callers`: list of `{ symbol, file, line }`
- `callees`: list of `{ symbol, file, line }`