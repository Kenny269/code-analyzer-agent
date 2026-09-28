---
name: impact-analysis
description: Analyze the impact of changing a symbol. Find what code is affected by modifying a function or class. Use when the user asks about impact, risk, blast radius, or what breaks if a symbol is changed.
---

# Impact Analysis

## Steps

1. Extract the target symbol name from the user request.
2. Query CodeGraph for impact with depth 2 using `codegraph impact <symbol> --depth 2`.
3. If no impact found, fall back to callers query.
4. Format results with risk level based on the number of affected symbols.

## Output Format

Return JSON with:
- `target`: the symbol name
- `affected`: list of affected symbols with file and depth
- `risk_level`: "low" | "medium" | "high"
- `total_affected`: count