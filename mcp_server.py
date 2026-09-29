#!/usr/bin/env python3
"""MCP Server for Code Analyzer Agent.

This server exposes the analyzer's capabilities as MCP tools,
so that AI IDEs (Cursor, VS Code, Claude Code) and agent platforms
can call them directly.
"""
import os
import json
import sys
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import MCPServer
from agent.orchestrator import Orchestrator
from agent.llm_client import LLMClient


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_ROOT = os.path.join(BASE_DIR, "skills")


# ---- 初始化编排器 ----

_llm: Optional[LLMClient] = None
try:
    _llm = LLMClient()
except ValueError:
    _llm = None

_orchestrator = Orchestrator(SKILLS_ROOT, llm=_llm)
_orchestrator.load_skills()


# ---- 创建 MCP Server ----

mcp = MCPServer(
    name="code-analyzer-agent",
    version="0.3.0",
    instructions=(
        "A code analysis agent for legacy systems. "
        "It can analyze project structure, call chains, impact, "
        "and extract business rules from source code."
    ),
)


@mcp.tool()
async def analyze_project(project_path: str, request: str = "提取这个系统的业务规则") -> str:
    """分析一个代码项目的结构、业务逻辑和潜在风险。

    Args:
        project_path: 项目的本地绝对路径或 Git 仓库 URL。
        request: 分析请求。常用值：
            - "提取这个系统的业务规则"
            - "分析项目结构"
            - "分析 <symbol> 的调用链"
            - "改动 <symbol> 的影响"

    Returns:
        一个 JSON 字符串，包含分析结果。
    """
    try:
        result = _orchestrator.run(request, project_path)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps(
            {"success": False, "error": str(e)},
            ensure_ascii=False,
        )


@mcp.tool()
async def list_skills() -> str:
    """列出当前可用的所有分析技能及其描述。

    Returns:
        一个 JSON 字符串，包含技能列表。
    """
    try:
        skills = _orchestrator.list_skills()
        return json.dumps({"skills": skills}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps(
            {"success": False, "error": str(e)},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    # stdio 传输是 IDE 集成的标准方式
    mcp.run(transport="stdio")