#!/usr/bin/env python3
"""Business rule extraction skill."""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient
from agent.llm_client import LLMClient


# 关键词分两类：
# 1. 符号名关键词：可能出现在函数名里的业务动作词
# 2. 文件名关键词：可能承载业务逻辑的文件
SYMBOL_KEYWORDS = [
    "create", "update", "delete", "add", "remove",
    "check", "validate", "verify", "calc", "compute",
    "apply", "process", "handle", "schedule", "filter",
    "priority", "status", "approve", "reject",
]

CORE_FILE_HINTS = ["service", "model", "scheduler", "filter", "repository", "storage"]


SYSTEM_PROMPT = """你是一个业务分析师，擅长从代码中提取业务规则。
用户会给你一段代码，请你识别其中蕴含的业务规则，用业务人员能听懂的自然语言描述。

要求：
1. 每条规则必须是一个完整的、独立的陈述，避免代码术语。
2. 每条规则必须附带代码位置引用。
3. 如果代码中没有明显的业务规则，返回空列表，不要编造。
4. 分类可选值：validation（校验）、calculation（计算）、workflow（流程）、constraint（约束）、other。

输出格式为 JSON：
{
  "rules": [
    {
      "description": "订单金额超过10万元需要二级审批",
      "category": "workflow",
      "code_reference": {"file": "...", "line_start": 1, "line_end": 10},
      "confidence": "high"
    }
  ]
}"""


def _normalize_query_result(result) -> list:
    """CodeGraph query 返回格式可能是 list 或 dict，统一成节点列表。"""
    if isinstance(result, list):
        return [item.get("node", item) for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        if "error" in result:
            return []
        items = result.get("results") or result.get("nodes") or []
        if isinstance(items, list):
            return [item.get("node", item) if isinstance(item, dict) else item for item in items]
    return []


def find_by_query(cg: CodeGraphClient) -> list:
    """用符号名关键词查询 CodeGraph。"""
    candidates = []
    seen = set()
    for kw in SYMBOL_KEYWORDS:
        result = cg.query(kw, limit=5)
        for node in _normalize_query_result(result):
            if not isinstance(node, dict):
                continue
            key = node.get("qualifiedName") or node.get("name", "")
            if key and key not in seen:
                seen.add(key)
                candidates.append(node)
    return candidates


def find_by_file_scan(project_path: str) -> list:
    """Fallback：直接扫描核心文件，提取函数定义。"""
    candidates = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".codegraph", "venv", ".venv"}]
        for f in files:
            if not f.endswith(".py"):
                continue
            if not any(hint in f.lower() for hint in CORE_FILE_HINTS):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, project_path)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines):
                m = re.match(r"^(\s*)def\s+(\w+)\s*\(", line)
                if m:
                    indent = len(m.group(1))
                    name = m.group(2)
                    end = i + 1
                    while end < len(lines):
                        nxt = lines[end]
                        if re.match(r"^\s*(def|class)\s+", nxt):
                            if len(nxt) - len(nxt.lstrip()) <= indent:
                                break
                        end += 1
                    candidates.append({
                        "name": name,
                        "qualifiedName": f"{f}::{name}",
                        "filePath": rel_path,
                        "startLine": i + 1,
                        "endLine": end,
                        "kind": "function",
                    })
    return candidates


def read_snippet(file_path: str, line_start: int, line_end: int, max_lines: int = 80) -> str:
    """读取指定行范围的代码片段。"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        start = max(0, line_start - 1)
        end = min(len(lines), line_end)
        if end - start > max_lines:
            end = start + max_lines
        return "".join(lines[start:end])
    except Exception:
        return ""


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]

    cg = CodeGraphClient(project_path)
    try:
        llm = LLMClient()
    except ValueError as e:
        print(json.dumps({
            "status": "error",
            "error": f"LLM not configured: {e}",
            "_meta": {"tokens": 0},
        }, ensure_ascii=False))
        return

    # 第一步：优先查图
    candidates = find_by_query(cg)

    # 第二步：如果图里没搜到，直接扫描核心文件
    if not candidates:
        candidates = find_by_file_scan(project_path)

    # 去重并限制数量
    seen = set()
    unique = []
    for c in candidates:
        key = c.get("qualifiedName") or f"{c.get('filePath')}::{c.get('name')}"
        if key not in seen:
            seen.add(key)
            unique.append(c)
    unique = unique[:10]

    if not unique:
        print(json.dumps({
            "status": "success",
            "data": {"rules": [], "total_rules": 0,
                     "note": "no candidate symbols found"},
            "error": None,
            "_meta": {"tokens": llm.total_tokens},
        }, ensure_ascii=False))
        return

    all_rules = []
    rule_counter = 0

    for cand in unique:
        file_path = os.path.join(project_path, cand.get("filePath", ""))
        line_start = cand.get("startLine", 1)
        line_end = cand.get("endLine", line_start + 50)

        snippet = read_snippet(file_path, line_start, line_end)
        if not snippet.strip():
            continue

        user_msg = (
            f"文件：{cand.get('filePath')}\n"
            f"符号：{cand.get('name')}\n"
            f"行范围：{line_start}-{line_end}\n\n"
            f"代码：\n```\n{snippet}\n```"
        )

        try:
            result = llm.chat_json(SYSTEM_PROMPT, user_msg, temperature=0.2)
        except Exception:
            continue

        for rule in result.get("rules", []):
            rule_counter += 1
            rule["id"] = f"BR-{rule_counter:03d}"
            all_rules.append(rule)

    print(json.dumps({
        "status": "success",
        "data": {"rules": all_rules, "total_rules": len(all_rules)},
        "error": None,
        "_meta": {"tokens": llm.total_tokens},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()