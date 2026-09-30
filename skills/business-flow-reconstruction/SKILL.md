---
name: business-flow-reconstruction
description: Reconstruct end-to-end business flows from code. Identify business entry points and trace through the calls that matter for business. Use when the user asks about business processes, workflows, end-to-end logic, or how a system handles a business scenario.
depends_on:
  - project-structure
  - business-rule-extraction
---

# Business Flow Reconstruction

## Purpose

Given a codebase, reconstruct the end-to-end business flows it implements, expressed in business language. The output should be understandable by non-technical stakeholders while retaining code references for verification.

## Steps

1. Use `previous_results` from `project-structure` to identify likely entry-point modules (controllers, handlers, CLI commands, message consumers).
2. Use CodeGraph to expand the call chain from each candidate entry point, limited to depth 5.
3. Filter out technical nodes (logging, utilities, serialization, getters/setters).
4. Use `previous_results` from `business-rule-extraction` to score remaining nodes on business relevance.
5. Use the LLM to group the business nodes into named flows and generate natural-language descriptions.
6. Output one entry per flow with ordered steps and a business summary.

## Output Format

Return JSON with:
- `flows`: list of `{ name, entry_point, steps, business_summary }`
- `total_flows`: count
- `disclaimer`: notice that flows are inferred and should be reviewed