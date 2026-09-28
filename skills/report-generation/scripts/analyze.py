#!/usr/bin/env python3
"""Report generation skill."""
import sys
import json
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.llm_client import LLMClient


SYSTEM_PROMPT = """你是一个技术写作专家。请把结构化的分析结果转成一份可读的中文报告。

要求：
1. 用 Markdown 格式。
2. 根据受众调整语气：技术人员用术语，业务人员用通俗语言。
3. 不要编造数据，只基于输入内容。
4. 报告应包含概述、主要发现、风险或建议。"""


def main():
    payload = json.loads(sys.stdin.read())
    input_data = payload["input"]

    audience = input_data.get("audience", "technical")
    previous_results = input_data.get("previous_results", {})
    analysis_result = input_data.get("analysis_result") or previous_results

    if not analysis_result:
        print(json.dumps({
            "status": "error",
            "error": "no analysis result provided. Run an analysis skill first.",
            "_meta": {"tokens": 0},
        }, ensure_ascii=False))
        return

    try:
        llm = LLMClient()
    except ValueError as e:
        print(json.dumps({
            "status": "error",
            "error": f"LLM not configured: {e}",
            "_meta": {"tokens": 0},
        }, ensure_ascii=False))
        return

    user_msg = (
        f"受众：{audience}\n\n"
        f"分析结果：\n{json.dumps(analysis_result, ensure_ascii=False, indent=2)}"
    )

    try:
        report = llm.chat(SYSTEM_PROMPT, user_msg, temperature=0.3)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "error": f"LLM call failed: {e}",
            "_meta": {"tokens": llm.total_tokens},
        }, ensure_ascii=False))
        return

    print(json.dumps({
        "status": "success",
        "data": {"report_markdown": report, "audience": audience},
        "error": None,
        "_meta": {"tokens": llm.total_tokens},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()