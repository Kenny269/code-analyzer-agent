#!/usr/bin/env python3
"""Call chain analysis skill."""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient


def extract_symbol(request: str) -> str:
    patterns = [
        r"调用链\s*[:：]?\s*(\S+)",
        r"调用者\s*[:：]?\s*(\S+)",
        r"(?:callers?|callees?|chain)\s+(?:of\s+)?(\S+)",
    ]
    for p in patterns:
        m = re.search(p, request, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", request)
    return tokens[-1] if tokens else ""


def main():
    payload = json.loads(sys.stdin.read())
    input_data = payload["input"]
    project_path = input_data["project_path"]
    user_request = input_data.get("user_request", "")
    params = input_data.get("params", {}) or {}

    symbol = params.get("symbol") or extract_symbol(user_request)

    if not symbol:
        print(json.dumps({
            "status": "error",
            "error": "could not determine target symbol. Try: '分析 create_task 的调用链'",
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