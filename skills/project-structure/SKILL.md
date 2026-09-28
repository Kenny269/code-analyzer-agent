---
name: project-structure
description: Analyze project structure, module layout, and file organization. Use when the user asks about project structure, modules, directories, architecture, or how the codebase is organized.
---

# Project Structure Analysis

## Steps

1. Query CodeGraph for the project's file structure using `codegraph files`.
2. Group files by top-level directory to identify modules.
3. Identify build files (pom.xml, package.json, requirements.txt, etc.).
4. Count files per module and identify module boundaries.

## Output Format

Return JSON with:
- `modules`: list of `{ name, path, file_count, files }`
- `build_system`: detected build system
- `total_files`: total code file count