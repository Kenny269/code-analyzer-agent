---
name: dead-code-detection
description: Detect suspected dead code, unused functions, or code that is defined but never called. Use when the user asks about dead code, unused code, orphaned functions, or what might be safely removed. Results require human review.
---

# Dead Code Detection

## Purpose

This skill produces a **suspected dead code list** for human review, not a final verdict. Static analysis cannot reliably detect all call paths (reflection, dynamic dispatch, framework callbacks, serialization hooks), so every result must be verified by a human before any code is removed.

## Steps

1. Scan the project for all symbol definitions (functions, methods, classes).
2. For each symbol, query CodeGraph for its callers.
3. Filter out obvious entry points, dunder methods, and test functions.
4. Assign a confidence level to each suspected symbol.
5. Attach a review hint describing what to check manually.
6. Sort by confidence (high first), then by file and line.

## Confidence Levels

- **high**: CodeGraph reports no callers, the symbol has a public name (not starting with `_`), and the name is not a common convention method (e.g. `to_dict`, `from_dict`, `__str__`).
- **medium**: No callers found, but the name is private (starts with `_`) or matches a common convention method, which may be invoked through reflection, serialization, or framework hooks.
- **low**: Caller query failed or returned an error. Cannot conclude anything.

## Output Format

Return JSON with:
- `dead_symbols`: list of `{ name, kind, file, line_start, confidence, review_hint }`
- `total_dead`: count
- `total_scanned`: total symbols scanned
- `scan_limited`: boolean, true if the scan was capped to avoid long runtime
- `disclaimer`: a human-readable notice that results require manual verification