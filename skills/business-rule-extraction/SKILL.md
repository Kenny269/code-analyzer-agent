---
name: business-rule-extraction
description: Extract business rules from code by locating business decision points such as conditions, state transitions, calculations, permissions, and business exceptions. Use when the user asks about business logic, business rules, domain constraints, or what the system does from a business perspective.
---

# Business Rule Extraction

## Purpose

Extract business rules that business stakeholders can understand. Rules are located by scanning for business decision points in code, not by matching function names.

## Steps

1. Extract business context from configuration files, SQL schemas, and entity definitions (enums, thresholds, constraints).
2. Scan code for business decision points:
   - Conditional branches involving amounts, quantities, states, or time
   - State transitions (status assignment, enum switching)
   - Calculations (tax, discount, points, amount)
   - Permission and ownership checks
   - Business exceptions (not null-pointer or technical errors)
3. Batch candidates and send each batch to the LLM with business context.
4. Merge and deduplicate rules that refer to the same business logic.
5. Group rules by business capability.

## Output Format

Return JSON with:
- `capabilities`: list of `{ name, rule_count, rules }` — rules grouped by business capability
- `rules`: flat list of all rules (for backward compatibility)
- `total_rules`: count
- `business_context`: extracted enums, thresholds, and constraints
- `_meta`: token usage