---
name: business-capability-map
description: Generate a high-level business capability map of the entire system. Automatically discover core modules and extract key business rules for each. Use when the user asks for system overview, capability map, or wants to understand what the system does.
---

# Business Capability Map

## Steps
1. Scan the project for Controller, Handler, or Service files.
2. Extract the domain names from file names.
3. For each domain, find key business rules using the LLM.
4. Group everything into a capability map.

## Output Format
Return JSON with:
- `domains`: list of `{ name, description }`
- `total_domains`: count