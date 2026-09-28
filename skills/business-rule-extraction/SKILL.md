---
name: business-rule-extraction
description: Extract business rules from code. Find validation logic, calculation rules, workflow constraints, and domain-specific conditions. Use when the user asks about business logic, business rules, domain constraints, or what the system does from a business perspective.
---

# Business Rule Extraction

## Steps

1. Use CodeGraph to locate functions that likely contain business logic (validation, calculation, state transition).
2. Read the relevant code snippets.
3. Send each snippet to the LLM with a prompt asking for business rules in natural language.
4. Cross-validate: if multiple snippets imply the same rule, merge them.
5. Output each rule with a code reference.

## Output Format

Return JSON with:
- `rules`: list of `{ id, description, category, code_references, confidence }`
- `total_rules`: count