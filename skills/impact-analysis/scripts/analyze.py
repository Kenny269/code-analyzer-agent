#!/usr/bin/env python3
"""Impact analysis skill."""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient


def extract_symbol(request: str) -> str:
    patterns = [
        r"影响\s*[:：]?\s*(\S+)",
        r"改动?\s*(\S+)",
        r"impact\s+(?:of\s+)?(\S+)",
    ]
    for p in patterns:
        m = re.search(p, request, re.IGNORECASE)
        if m:
            return m.group(1).strip()
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
            "error": "could not extract symbol name",
        }, ensure_ascii=False))
        return

    cg = CodeGraphClient(project_path)
    impact = cg.impact(symbol, depth=2)

    if isinstance(impact, dict) and "error" in impact:
        # fallback: 用 callers 近似
        impact = cg.callers(symbol)

    affected = []
    if isinstance(impact, list):
        affected = impact
    elif isinstance(impact, dict):
        affected = impact.get("affected", impact.get("nodes", []))

    total = len(affected)
    if total <= 3:
        risk = "low"
    elif total <= 10:
        risk = "medium"
    else:
        risk = "high"

    result = {
        "status": "success",
        "data": {
            "target": symbol,
            "affected": affected[:100],
            "risk_level": risk,
            "total_affected": total,
        },
        "error": None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()