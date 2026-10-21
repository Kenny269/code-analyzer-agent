#!/usr/bin/env python3
"""Business rule extraction skill with focus-driven scanning."""
import sys
import json
import os
import re
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.llm_client import LLMClient


# 严格忽略的目录（前端、依赖、测试）
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".codegraph", "venv", ".venv", "node_modules",
    "dist", "build", "target", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", "docs", "static", "public", "assets", "test", "tests", "mock",
    "frontend", "admin", "web", "vue", "react", "ui"
}

CODE_EXTENSIONS = {".py", ".java", ".go", ".rs", ".rb", ".php", ".kt", ".scala"}
CONFIG_EXTENSIONS = {".properties", ".yml", ".yaml", ".toml", ".ini"}
SQL_EXTENSIONS = {".sql"}

MAX_CODE_FILES = 120
MAX_CANDIDATES = 80
MAX_PER_FILE = 10  # 新增：单文件最多贡献10个决策点，防止单一巨型文件垄断
BATCH_SIZE = 15
SNIPPET_CONTEXT_LINES = 3

# 业务特征词（用于打分）
CORE_PATHS = {"service", "biz", "domain", "logic", "core", "trade", "order"}
BUSINESS_CONDITION_KEYWORDS = [
    "amount", "price", "total", "balance", "credit", "debit",
    "quantity", "stock", "inventory", "status", "state", "stage",
    "role", "permission", "owner", "coupon", "discount", "promotion",
    "points", "score", "expire", "deadline", "limit", "threshold",
    "level", "grade", "vip", "order", "pay", "refund"
]

def score_file(rel_path: str, focus: list) -> int:
    """给文件打分，决定优先级。"""
    lower = rel_path.lower()
    score = 0

    # 路径中包含 focus 词汇，极大加分
    for f in focus:
        if f in lower:
            score += 100

    # 路径包含业务核心层，加分
    for core in CORE_PATHS:
        if f"/{core}/" in lower or f"\\{core}\\" in lower:
            score += 50

    # 纯配置或底层代码降权
    if "config" in lower or "common" in lower or "util" in lower:
        score -= 20

    return score

def should_skip_file(rel_path: str) -> bool:
    lower = rel_path.lower()
    parts = re.split(r"[\\/]", lower)
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    return False

def extract_business_context(project_path: str) -> dict:
    context = {"configs": [], "sql_enums": [], "sql_constraints": []}
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            full = os.path.join(root, f)
            rel = os.path.relpath(full, project_path)
            if should_skip_file(rel): continue

            if ext in CONFIG_EXTENSIONS:
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        for i, line in enumerate(fh, 1):
                            stripped = line.strip()
                            if not stripped or stripped.startswith(("#", "//")): continue
                            if re.search(r"(limit|max|min|threshold|timeout|expire|rate|amount|quota)", stripped, re.IGNORECASE):
                                context["configs"].append({"file": rel, "line": i, "content": stripped[:200]})
                except: pass
            elif ext in SQL_EXTENSIONS:
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    for m in re.finditer(r"ENUM\s*\(([^)]+)\)", content, re.IGNORECASE):
                        vals = re.findall(r"'([^']+)'", m.group(1))
                        if vals: context["sql_enums"].append({"file": rel, "values": vals[:20]})
                except: pass

    context["configs"] = context["configs"][:20]
    context["sql_enums"] = context["sql_enums"][:15]
    return context

def scan_decision_points(file_path: str, rel_path: str) -> list:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except: return []

    candidates = []
    seen_lines = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")) or len(stripped) < 10: continue

        dtype = None
        # 简单规则：包含 if/switch/when 且包含业务词
        if re.match(r"^(?:if|elif|else if|when|case|switch)\b", stripped, re.IGNORECASE):
            if any(kw in stripped.lower() for kw in BUSINESS_CONDITION_KEYWORDS):
                dtype = "condition"
        
        # 异常包含业务词
        if not dtype and re.search(r"\b(?:raise|throw)\b", stripped, re.IGNORECASE):
            if any(kw in stripped.lower() for kw in BUSINESS_CONDITION_KEYWORDS):
                dtype = "exception"

        if dtype and i not in seen_lines:
            seen_lines.add(i)
            start = max(0, i - SNIPPET_CONTEXT_LINES)
            end = min(len(lines), i + SNIPPET_CONTEXT_LINES + 1)
            candidates.append({
                "file": rel_path, "line": i + 1, "type": dtype, "snippet": "".join(lines[start:end])[:800]
            })
    return candidates

def collect_candidates(project_path: str, focus: list) -> list:
    scored_files = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in CODE_EXTENSIONS: continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, project_path)
            if should_skip_file(rel): continue
            
            score = score_file(rel, focus)
            if focus and score < 0: continue
            scored_files.append((score, full, rel))

    # 按得分从高到低排序
    scored_files.sort(key=lambda x: x[0], reverse=True)
    
    all_candidates = []
    for score, full, rel in scored_files[:MAX_CODE_FILES]:
        file_candidates = scan_decision_points(full, rel)
        
        # 限制单个文件贡献的候选点数量
        if len(file_candidates) > MAX_PER_FILE:
            # 尽量均匀分布地取
            step = max(1, len(file_candidates) // MAX_PER_FILE)
            file_candidates = file_candidates[::step][:MAX_PER_FILE]
            
        all_candidates.extend(file_candidates)
        if len(all_candidates) >= MAX_CANDIDATES:
            break

    return all_candidates[:MAX_CANDIDATES]

SYSTEM_PROMPT = """你是一个资深业务分析师。用户会给你一批从代码中提取的业务决策点。
请提取业务规则，用业务人员能听懂的语言描述。

要求：
1. 剔除纯技术代码（如判空、日志、对象初始化、权限框架的通用校验）。
2. 规则必须包含代码位置引用（文件+行号）。
3. 分类：validation, calculation, workflow, constraint, permission。
4. 尝试把规则归纳到合理的业务能力（capability）下（如：订单履约、营销规则）。

输出 JSON：
{
  "rules": [
    {"description": "...", "category": "...", "capability": "...", "code_reference": {"file": "...", "line_start": 1}, "confidence": "high"}
  ]
}"""

def extract_rules_batch(llm: LLMClient, candidates: list, context: dict) -> list:
    if not candidates: return []
    user_msg = (
        f"业务上下文：\n{json.dumps(context, ensure_ascii=False)[:3000]}\n\n"
        f"候选片段：\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    try:
        result = llm.chat_json(SYSTEM_PROMPT, user_msg, temperature=0.2)
        return result.get("rules", [])
    except: return []

def deduplicate_rules(rules: list) -> list:
    seen = set()
    unique = []
    for r in rules:
        key = r.get("description", "")[:20]
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

def group_by_capability(rules: list) -> list:
    groups = {}
    for r in rules:
        cap = r.get("capability") or "未分类"
        groups.setdefault(cap, []).append(r)
    return [{"name": k, "rule_count": len(v), "rules": v} for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))]

def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]
    params = payload["input"].get("params", {}) or {}
    focus = [f.lower() for f in params.get("focus", []) if isinstance(f, str)]

    try: llm = LLMClient()
    except: 
        print(json.dumps({"status": "error", "error": "LLM not configured"}))
        return

    context = extract_business_context(project_path)
    candidates = collect_candidates(project_path, focus)

    if not candidates:
        print(json.dumps({"status": "success", "data": {"capabilities": [], "rules": [], "stats": {"candidates_scanned": 0}}}))
        return

    all_rules = []
    for i in range(0, len(candidates), BATCH_SIZE):
        all_rules.extend(extract_rules_batch(llm, candidates[i:i+BATCH_SIZE], context))

    all_rules = deduplicate_rules(all_rules)
    for idx, r in enumerate(all_rules, 1):
        r["id"] = f"BR-{idx:03d}"

    capabilities = group_by_capability(all_rules)

    print(json.dumps({
        "status": "success",
        "data": {
            "capabilities": capabilities,
            "rules": all_rules,
            "total_rules": len(all_rules),
            "stats": {
                "candidates_scanned": len(candidates),
                "rules_extracted": len(all_rules),
                "capabilities_found": len(capabilities)
            }
        },
        "_meta": {"tokens": llm.total_tokens}
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()