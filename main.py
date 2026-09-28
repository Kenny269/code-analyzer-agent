#!/usr/bin/env python3
"""Code Analyzer Agent — 入口。"""
import sys
import os
import json

from dotenv import load_dotenv
load_dotenv()

from agent.orchestrator import Orchestrator
from agent.llm_client import LLMClient


SKILLS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 main.py <project_path> <request>")
        print("Example: python3 main.py /path/to/project '分析项目结构'")
        sys.exit(1)

    project_path = sys.argv[1]
    user_request = " ".join(sys.argv[2:])

    llm = None
    try:
        llm = LLMClient()
        print(f"LLM enabled: {llm.model} @ {llm.base_url}")
    except ValueError as e:
        print(f"LLM disabled ({e}), using keyword matching.")

    orch = Orchestrator(SKILLS_ROOT, llm=llm)
    skills = orch.load_skills()

    print(f"Loaded {len(skills)} skills:")
    for s in skills:
        print(f"  - {s.name}")

    result = orch.run(user_request, project_path)
    print("\n" + "=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    selector_tokens = llm.total_tokens if llm else 0
    skill_tokens = 0
    if isinstance(result, dict):
        meta = result.get("_meta", {})
        if isinstance(meta, dict):
            skill_tokens = meta.get("skill_tokens", 0)
    print(f"Selector tokens: {selector_tokens}")
    print(f"Skill tokens:    {skill_tokens}")
    print(f"Total tokens:    {selector_tokens + skill_tokens}")


if __name__ == "__main__":
    main()