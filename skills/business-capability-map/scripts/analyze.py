#!/usr/bin/env python3
"""Business capability map skill."""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.llm_client import LLMClient

EXCLUDE_DIRS = {".git", "node_modules", "dist", "build", "target", "test", "frontend", "admin"}
CODE_EXTS = {".java", ".py", ".go", ".js", ".ts"}

SYSTEM_PROMPT = """你是一个资深业务架构师。用户会给你一组代码文件路径和类名。
请推断出这个系统包含哪些核心业务模块（领域），并为每个模块写出1-2句话的概述。

输出 JSON：
{
  "domains": [
    {"name": "订单履约", "description": "负责订单创建、状态流转、发货与售后处理。"}
  ]
}"""

def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]

    try: llm = LLMClient()
    except: 
        print(json.dumps({"status": "error", "error": "LLM not configured"}))
        return

    candidates = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in CODE_EXTS: continue
            if "Controller" in f or "Service" in f or "Handler" in f:
                candidates.append(f)

    if not candidates:
        print(json.dumps({"status": "success", "data": {"domains": [], "total_domains": 0}}))
        return

    unique_names = list(set(candidates))[:50]
    user_msg = "核心类文件列表：\n" + "\n".join(unique_names)
    
    try:
        res = llm.chat_json(SYSTEM_PROMPT, user_msg, temperature=0.3)
        domains = res.get("domains", [])
    except:
        domains = []

    print(json.dumps({
        "status": "success",
        "data": {"domains": domains, "total_domains": len(domains)},
        "_meta": {"tokens": llm.total_tokens}
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()