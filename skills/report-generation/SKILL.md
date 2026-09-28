---
name: report-generation
description: Generate a human-readable report from analysis results. Use when the user asks for a summary, report, or wants results presented in a readable format. Usually runs after other analysis skills have produced results.
---

# Report Generation

## Steps

1. Receive analysis results (JSON) from previous skills or from the project itself.
2. Use the LLM to convert structured data into a natural language report.
3. Tailor the report to the audience: technical (developers) or business (non-technical).

## Output Format

Return JSON with:
- `report_markdown`: the report in Markdown
- `audience`: "technical" or "business"