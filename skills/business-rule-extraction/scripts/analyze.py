#!/usr/bin/env python3
"""Business rule extraction skill with document cross-validation."""
import sys
import json
import os
import re
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.llm_client import LLMClient

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
MAX_PER_FILE = 10
BATCH_SIZE = 15
SNIPPET_CONTEXT_LINES = 3

CORE_PATHS = {"service", "biz", "domain", "logic", "core", "trade", "order"}
BUSINESS_CONDITION_KEYWORDS = [
    "amount", "price", "total", "balance", "credit", "debit",
    "quantity", "stock", "inventory", "status", "state", "stage",
    "role", "permission", "owner", "coupon", "discount", "promotion",
    "points", "score", "expire", "deadline", "limit", "threshold",
    "level", "grade", "vip", "order", "pay", "refund", "cancel"
]

def extract_keywords_from_doc(doc: str) -> list:
    """从业务文档中提取核心名词/动词，用于辅助文件打分。"""
    if not doc: return []
    # 简单提取：找出现频率高的中文/英文业务词
    words = re.findall(r"[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}", doc)
    freq = defaultdict(int)
    for w in words:
        w_lower = w.lower()
        if w_lower in ["订单", "用户", "支付", "状态", "金额", "系统", "功能", "操作", "查询", "如果", "可以", "需要"]:
            continue
        freq[w_lower] += 1
    # 取频次最高的前5个词
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, count in sorted_words[:5] if count >= 2]

def score_file(rel_path: str, focus: list) -> int:
    lower = rel_path.lower()
    score = 0
    for f in focus:
        if f in lower: score += 100
    for core in CORE_PATHS:
        if f"/{core}/" in lower or f"\\{core}\\" in lower: score += 50
    if "config" in lower or "common" in lower or "util" in lower: score -= 20
    return score

def should_skip_file(rel_path: str) -> bool:
    lower = rel_path.lower()
    parts = re.split(r"[\\/]", lower)
    return any(part in EXCLUDE_DIRS for part in parts)

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
        if re.match(r"^(?:if|elif|else if|when|case|switch)\b", stripped, re.IGNORECASE):
            if any(kw in stripped.lower() for kw in BUSINESS_CONDITION_KEYWORDS): dtype = "condition"
        if not dtype and re.search(r"\b(?:raise|throw)\b", stripped, re.IGNORECASE):
            if any(kw in stripped.lower() for kw in BUSINESS_CONDITION_KEYWORDS): dtype = "exception"
        if dtype and i not in seen_lines:
            seen_lines.add(i)
            start = max(0, i - SNIPPET_CONTEXT_LINES)
            end = min(len(lines), i + SNIPPET_CONTEXT_LINES + 1)
            candidates.append({"file": rel_path, "line": i + 1, "type": dtype, "snippet": "".join(lines[start:end])[:800]})
    return candidates

def sample_candidates_uniformly(candidates: list, max_per_file: int) -> list:
    """均匀采样：对于长文件，在文件头、中、尾分别取样，避免只截取到前面的逻辑"""
    if len(candidates) <= max_per_file:
        return candidates
    
    step = max(1, len(candidates) // max_per_file)
    sampled = []
    for i in range(0, len(candidates), step):
        sampled.append(candidates[i])
        if len(sampled) >= max_per_file:
            break
    return sampled

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
    scored_files.sort(key=lambda x: x[0], reverse=True)
    
    all_candidates = []
    for score, full, rel in scored_files[:MAX_CODE_FILES]:
        file_candidates = scan_decision_points(full, rel)
        # 改为均匀采样
        file_candidates = sample_candidates_uniformly(file_candidates, MAX_PER_FILE)
        all_candidates.extend(file_candidates)
        if len(all_candidates) >= MAX_CANDIDATES: break
    return all_candidates[:MAX_CANDIDATES]

def extract_rules_batch(llm: LLMClient, candidates: list, context: dict, business_doc: str) -> list:
    if not candidates: return []
    
    doc_section = f"\n【参考业务文档】\n{business_doc[:3000]}\n" if business_doc else ""
    
    if business_doc:
        sys_prompt = """你是一个资深业务审计师。你的任务是：**先从代码片段中提取所有真实的业务规则**，然后再将该规则与【参考业务文档】进行比对。

请严格遵循以下步骤：
1. 忽略纯技术代码（判空、日志、ORM映射）。
2. 找出代码里的核心业务判断（如状态流转、金额计算、拦截条件）。
3. 对照参考文档，给每条规则打上 status 标签：
   - consistent：代码实现与文档描述一致。
   - conflict：代码实现与文档描述冲突。
   - missing：文档描述了，但当前代码片段中确实没找到对应逻辑。
   - hidden：代码里有复杂的隐藏逻辑（如硬编码、特殊判断），但文档未提及。

注意：**即使文档里没提，只要代码里写了重要业务规则，你也必须提取出来，并标为 hidden！** 不要被文档限制住了视野。

输出 JSON：
{
  "rules": [
    {
      "description": "提取出的业务规则描述",
      "category": "validation|calculation|workflow|constraint|permission",
      "capability": "业务能力名称",
      "status": "consistent|conflict|missing|hidden",
      "explanation": "解释为什么给出这个状态（对照文档哪句话，或指出代码里的隐藏逻辑）",
      "code_reference": {"file": "...", "line_start": 1},
      "confidence": "high"
    }
  ]
}"""
    else:
        sys_prompt = """你是一个资深业务分析师。请提取业务规则。
要求：
1. 剔除纯技术代码。
2. 规则必须包含代码位置引用。
3. 分类：validation, calculation, workflow, constraint, permission。
4. 归纳业务能力（capability）。

输出 JSON：
{
  "rules": [
    {"description": "...", "category": "...", "capability": "...", "code_reference": {"file": "...", "line_start": 1}, "confidence": "high"}
  ]
}"""

    user_msg = (
        f"业务上下文（配置/SQL）：\n{json.dumps(context, ensure_ascii=False)[:1500]}\n"
        f"{doc_section}\n"
        f"代码候选片段：\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    
    try:
        result = llm.chat_json(sys_prompt, user_msg, temperature=0.2)
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
    business_doc = payload["input"].get("business_doc", "")
    
    # 1. 基础 focus 词汇
    focus = [f.lower() for f in params.get("focus", []) if isinstance(f, str)]
    
    # 2. 从文档中提取额外关键词，并入 focus
    if business_doc:
        doc_keywords = extract_keywords_from_doc(business_doc)
        focus.extend(doc_keywords)
        focus = list(set(focus)) # 去重

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
        all_rules.extend(extract_rules_batch(llm, candidates[i:i+BATCH_SIZE], context, business_doc))

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