---
name: dependency-cycle-detection
description: Detect circular dependencies between modules or files. Use when the user asks about circular dependencies, dependency cycles, tightly coupled modules, or refactoring blockers.
---

# Dependency Cycle Detection

## Purpose

Identify circular dependencies between modules in a codebase. Circular dependencies are a common blocker for refactoring and often indicate architectural problems.

## Steps

1. Scan all code files in the project.
2. Extract import/require/include statements from each file.
3. Map imported names to internal project files (ignore external dependencies).
4. Build a directed graph of file-level dependencies.
5. Find all strongly connected components with more than one node (cycles).
6. Sort cycles by size (largest first).

## Output Format

Return JSON with:
- `cycles`: list of `{ files, size, severity }`
- `total_cycles`: count
- `total_files_scanned`: total files analyzed
- `total_edges`: total dependency edges