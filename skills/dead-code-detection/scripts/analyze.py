#!/usr/bin/env python3
"""Dead code detection skill.

Produces a suspected dead code list for human review.
Static analysis cannot reliably detect all call paths.
"""
import sys
import json
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient


SKIP_DIRS = {".git", "__pycache__", ".codegraph", "venv", ".venv",
             "node_modules", "dist", "build", "target", ".tox", ".mypy_cache"}

CODE_EXTENSIONS = {".py", ".java", ".js", ".ts", ".go", ".c", ".cpp",
                   ".h", ".hpp", ".cs", ".rb", ".php"}

ENTRY_NAMES = {
    "main", "__main__", "init", "setup", "run", "start", "handler",
    "on_load", "on_start", "on_ready", "on_message", "on_event",
}

# 常见的约定方法名，可能通过反射、序列化、框架钩子调用
CONVENTION_NAMES = {
    "to_dict", "from_dict", "to_json", "from_json", "to_string",
    "to_string_repr", "__str__", "__repr__", "__eq__", "__hash__",
    "serialize", "deserialize", "clone", "copy", "get", "set",
}

MAX_SYMBOLS = 60

DISCLAIMER = (
    "This is a suspected dead code list for human review. "
    "Static analysis may miss calls via reflection, dynamic dispatch, "
    "framework callbacks, or serialization hooks. "
    "Verify each entry before removing any code."
)


def should_skip(name: str) -> bool:
    if not name:
        return True
    if name.startswith("__") and name.endswith("__"):
        return True
    if name.startswith("test_") or name.endswith("_test"):
        return True
    if name in ENTRY_NAMES:
        return True
    return False


def extract_python_symbols(file_path: str, lines: list):
    symbols = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(def|class)\s+(\w+)\s*[\(:]", line)
        if m:
            kind = "function" if m.group(2) == "def" else "class"
            symbols.append({
                "name": m.group(3),
                "kind": kind,
                "line_start": i + 1,
            })
    return symbols


def extract_generic_symbols(file_path: str, lines: list):
    symbols = []
    patterns = [
        (re.compile(r"^\s*(?:public|private|protected|static|async|export)?\s*(?:function|func|fn)\s+(\w+)\s*\("), "function"),
        (re.compile(r"^\s*(?:public|private|abstract|final|export)?\s*(?:class|interface|struct)\s+(\w+)"), "class"),
    ]
    for i, line in enumerate(lines):
        for pat, kind in patterns:
            m = pat.match(line)
            if m:
                symbols.append({
                    "name": m.group(1),
                    "kind": kind,
                    "line_start": i + 1,
                })
                break
    return symbols


def scan_symbols(project_path: str) -> list:
    symbols = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, project_path)
            if "test" in rel_path.lower() or "spec" in rel_path.lower():
                continue
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except Exception:
                continue

            if ext == ".py":
                extracted = extract_python_symbols(full_path, lines)
            else:
                extracted = extract_generic_symbols(full_path, lines)

            for s in extracted:
                s["file"] = rel_path
                symbols.append(s)
    return symbols


def query_callers(cg: CodeGraphClient, symbol: str):
    """返回 (has_callers, status)。status 为 'ok' 或 'error'。"""
    result = cg.callers(symbol)
    if isinstance(result, dict):
        if "error" in result:
            return True, "error"
        callers = result.get("callers", [])
        return len(callers) > 0, "ok"
    if isinstance(result, list):
        return len(result) > 0, "ok"
    return True, "error"


def classify(symbol_name: str, file_path: str, query_status: str) -> tuple:
    """返回 (confidence, review_hint)。"""
    if query_status == "error":
        return "low", "Caller query failed. Re-run analysis or inspect manually."

    hints = []
    confidence = "high"

    if symbol_name.startswith("_"):
        confidence = "medium"
        hints.append("Private method. May be called via reflection or internally.")

    if symbol_name in CONVENTION_NAMES:
        confidence = "medium"
        hints.append("Common convention name. May be invoked via serialization or framework hooks.")

    if "model" in file_path.lower():
        if confidence == "high":
            confidence = "medium"
        hints.append("File appears to define data models. Methods here are often called by ORM or serialization.")

    if not hints:
        hints.append("No callers found. Verify with grep or IDE 'Find Usages' before removing.")

    return confidence, " ".join(hints)


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]

    cg = CodeGraphClient(project_path)

    all_symbols = scan_symbols(project_path)
    total_scanned = len(all_symbols)

    candidates = [s for s in all_symbols if not should_skip(s["name"])]

    scan_limited = False
    if len(candidates) > MAX_SYMBOLS:
        candidates = candidates[:MAX_SYMBOLS]
        scan_limited = True

    dead_symbols = []
    for s in candidates:
        has_callers, status = query_callers(cg, s["name"])
        if has_callers:
            continue
        confidence, review_hint = classify(s["name"], s["file"], status)
        dead_symbols.append({
            "name": s["name"],
            "kind": s["kind"],
            "file": s["file"],
            "line_start": s["line_start"],
            "confidence": confidence,
            "review_hint": review_hint,
        })

    # 排序：先按置信度，再按文件和行号
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    dead_symbols.sort(key=lambda x: (
        confidence_order.get(x["confidence"], 3),
        x["file"],
        x["line_start"],
    ))

    # 统计各置信度数量
    counts = {"high": 0, "medium": 0, "low": 0}
    for s in dead_symbols:
        counts[s["confidence"]] += 1

    print(json.dumps({
        "status": "success",
        "data": {
            "dead_symbols": dead_symbols,
            "total_dead": len(dead_symbols),
            "confidence_counts": counts,
            "total_scanned": total_scanned,
            "scan_limited": scan_limited,
            "disclaimer": DISCLAIMER,
        },
        "error": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()