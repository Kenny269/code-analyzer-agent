#!/usr/bin/env python3
"""Business flow reconstruction skill.

Consumes results from project-structure and business-rule-extraction,
expands call chains via CodeGraph, and uses the LLM to name and describe
business flows.
"""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient
from agent.llm_client import LLMClient


# 入口文件候选名
ENTRY_FILE_NAMES = {
    "main.py", "app.py", "cli.py", "cmd.py", "commands.py",
    "handler.py", "handlers.py", "controller.py", "controllers.py",
    "api.py", "routes.py", "endpoints.py", "server.py",
    "Main.java", "App.java", "Application.java",
    "main.go", "main.rs",
}

# 扫描时跳过的目录
SKIP_DIRS = {".git", "__pycache__", ".codegraph", "venv", ".venv",
             "node_modules", "dist", "build", "target", ".tox"}

# 入口候选函数名里不应包含的前缀
ENTRY_FUNC_EXCLUDE_PREFIXES = ("_", "build_", "get_", "set_", "make_", "new_")

# 技术性节点名字里包含这些词的，过滤掉
TECHNICAL_KEYWORDS = {
    "log", "logger", "util", "helper", "format", "parse", "serialize",
    "deserialize", "to_", "from_", "encode", "decode",
    "cache", "lock", "mutex", "thread", "sleep", "retry",
}

# 业务性节点名字里包含这些词的，加分
BUSINESS_KEYWORDS = {
    "create", "update", "delete", "add", "remove", "submit", "approve",
    "reject", "pay", "charge", "refund", "reserve", "confirm", "cancel",
    "notify", "send", "publish", "subscribe", "validate", "check",
    "process", "handle", "execute", "apply", "list", "schedule",
}

MAX_ENTRY_POINTS = 5
MAX_CHAIN_DEPTH = 4
MAX_STEPS_PER_FLOW = 10


def is_technical(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in TECHNICAL_KEYWORDS)


def is_business(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in BUSINESS_KEYWORDS)


def _normalize_query_result(result) -> list:
    if isinstance(result, list):
        return [item.get("node", item) for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        if "error" in result:
            return []
        items = result.get("results") or result.get("nodes") or []
        if isinstance(items, list):
            return [item.get("node", item) if isinstance(item, dict) else item
                    for item in items]
    return []


def scan_entry_files(project_path: str) -> list:
    """扫描入口文件中的顶层函数定义。"""
    entries = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f not in ENTRY_FILE_NAMES:
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, project_path)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines):
                # Python: def foo(...)
                m = re.match(r"^def\s+(\w+)\s*\(", line)
                if not m:
                    # Java/Go: public/private/static ... foo(...) {
                    m = re.match(
                        r"^\s*(?:public|private|protected|static|func|fn)\s+(?:\w+\s+)*(\w+)\s*\(",
                        line
                    )
                if m:
                    name = m.group(1)
                    if name.startswith(ENTRY_FUNC_EXCLUDE_PREFIXES):
                        continue
                    entries.append({
                        "name": name,
                        "qualifiedName": f"{rel_path}::{name}",
                        "filePath": rel_path,
                        "startLine": i + 1,
                        "source": "file_scan",
                    })
    return entries


def find_entry_points(cg: CodeGraphClient, project_path: str,
                      project_structure: dict) -> list:
    """从入口文件中找出候选业务入口点。"""
    entries = scan_entry_files(project_path)

    # 兜底：用 CodeGraph 搜常见入口名
    if not entries:
        for keyword in ["main", "run", "handle", "process", "execute"]:
            result = cg.query(keyword, limit=5)
            for node in _normalize_query_result(result):
                if isinstance(node, dict) and node.get("name"):
                    entries.append(node)

    # 去重
    seen = set()
    unique = []
    for e in entries:
        key = e.get("qualifiedName") or e.get("name", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(e)
    return unique[:MAX_ENTRY_POINTS]


def expand_chain(cg: CodeGraphClient, symbol: str, depth: int,
                 visited: set) -> list:
    """递归展开调用链，返回节点列表。"""
    if depth <= 0 or not symbol or symbol in visited:
        return []
    visited.add(symbol)

    result = cg.callees(symbol)
    callees = []
    if isinstance(result, dict) and "error" not in result:
        callees = result.get("callees", [])
    elif isinstance(result, list):
        callees = result

    nodes = []
    for c in callees:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "")
        if not name:
            continue
        if is_technical(name):
            continue
        node = {
            "name": name,
            "kind": c.get("kind", "function"),
            "file": c.get("filePath", ""),
            "line": c.get("startLine", 0),
            "depth": MAX_CHAIN_DEPTH - depth + 1,
        }
        nodes.append(node)
        if is_business(name) and depth > 1:
            nodes.extend(expand_chain(cg, name, depth - 1, visited))

    return nodes


LLM_PROMPT = """你是一个业务分析师。用户会给你一组从代码中提取的调用链，
请你把它们组织成人类能理解的业务流程，并用业务语言描述。

要求：
1. 每个流程有一个业务化的名称（比如"下单流程"，不要用"createOrder"）。
2. 每个流程包含 3-8 个关键步骤，按业务上的时间顺序排列。
3. 每个步骤用一句话描述业务含义，不要包含代码术语。
4. 保留代码位置引用（文件名 + 行号）。
5. 如果调用链不能构成完整业务流程，返回空列表，不要编造。
6. 尽量合并重复的调用链，不要为每个入口都生成一个流程。

输出格式为 JSON：
{
  "flows": [
    {
      "name": "下单流程",
      "entry_point": {"symbol": "...", "file": "...", "line": 45},
      "steps": [
        {
          "order": 1,
          "name": "创建订单",
          "symbol": "OrderService.create",
          "file": "service/OrderService.java",
          "line": 30,
          "description": "校验订单信息并写入数据库"
        }
      ],
      "business_summary": "用户下单后，系统依次执行订单创建、库存预留、支付扣款。"
    }
  ]
}"""


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]
    previous = payload["input"].get("previous_results", {})

    project_structure = previous.get("project-structure", {})
    business_rules = previous.get("business-rule-extraction", {})

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

    entries = find_entry_points(cg, project_path, project_structure)
    if not entries:
        print(json.dumps({
            "status": "success",
            "data": {"flows": [], "total_flows": 0,
                     "disclaimer": "No business entry points found."},
            "error": None,
            "_meta": {"tokens": llm.total_tokens},
        }, ensure_ascii=False))
        return

    # 展开每个入口点的调用链
    chains = []
    for entry in entries:
        symbol = entry.get("qualifiedName") or entry.get("name", "")
        visited = set()
        nodes = expand_chain(cg, symbol, MAX_CHAIN_DEPTH, visited)

        # 即使展开失败，也把入口本身作为一步
        if not nodes:
            nodes = [{
                "name": entry.get("name", ""),
                "kind": "function",
                "file": entry.get("filePath", ""),
                "line": entry.get("startLine", 0),
                "depth": 1,
            }]

        chains.append({
            "entry_point": {
                "symbol": symbol,
                "name": entry.get("name", ""),
                "file": entry.get("filePath", ""),
                "line": entry.get("startLine", 0),
            },
            "nodes": nodes[:MAX_STEPS_PER_FLOW],
        })

    # 送 LLM 组织成流程
    user_msg = (
        f"业务规则参考（来自前置分析）：\n"
        f"{json.dumps(business_rules.get('rules', [])[:10], ensure_ascii=False, indent=2)}\n\n"
        f"调用链（来自代码分析）：\n"
        f"{json.dumps(chains, ensure_ascii=False, indent=2)}"
    )

    try:
        result = llm.chat_json(LLM_PROMPT, user_msg, temperature=0.2)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "error": f"LLM call failed: {e}",
            "_meta": {"tokens": llm.total_tokens},
        }, ensure_ascii=False))
        return

    flows = result.get("flows", [])

    print(json.dumps({
        "status": "success",
        "data": {
            "flows": flows,
            "total_flows": len(flows),
            "disclaimer": (
                "Business flows are inferred from static analysis and require "
                "human review. Verify each flow against actual business requirements."
            ),
        },
        "error": None,
        "_meta": {"tokens": llm.total_tokens},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()