#!/usr/bin/env python3
"""Call chain analysis skill."""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient


def extract_symbol(request: str) -> str:
    """从用户请求中提取符号名。简单实现，将来可升级为 LLM 抽取。"""
    # 尝试匹配：调用链/调用者/callers of XXX
    patterns = [
        r"调用链\s*[:：]?\s*(\S+)",
        r"调用者\s*[:：]?\s*(\S+)",
        r"(?:callers?|callees?|chain)\s+(?:of\s+)?(\S+)",
    ]
    for p in patterns:
        m = re.search(p, request, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # fallback: 取最后一个看起来像标识符的 token
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", request)
    return tokens[-1] if tokens else ""


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]
    user_request = payload["input"].get("user_request", "")

    symbol = extract_symbol(user_request)
    if not symbol:
        print(json.dumps({
            "status": "error",
            "error": "could not extract symbol name from request",
            "hint": "try: '分析 AuthService.login 的调用链'",
        }, ensure_ascii=False))
        return

    cg = CodeGraphClient(project_path)
    callers = cg.callers(symbol)
    callees = cg.callees(symbol)

    result = {
        "status": "success",
        "data": {
            "target": symbol,
            "callers": callers if not isinstance(callers, dict) or "error" not in callers else [],
            "callees": callees if not isinstance(callees, dict) or "error" not in callees else [],
        },
        "error": None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()