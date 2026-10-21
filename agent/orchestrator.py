import os
import json
from typing import List, Optional, Any, Callable
from .skill_loader import SkillLoader, SkillMeta
from .skill_runner import SkillRunner
from .llm_client import LLMClient


ProgressCallback = Optional[Callable[[str, dict], None]]


class LLMSelector:
    """用 LLM 从自然语言请求中提取技能、参数和澄清问题。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def select_with_params(self, user_request: str, skills: List[SkillMeta]) -> dict:
        if not skills:
            return {"skills": [], "params": {}, "clarification": None}
        if len(skills) == 1:
            return {"skills": [skills[0]], "params": {}, "clarification": None}

        skill_list = "\n".join(
            f"- {s.name}: {s.description}" for s in skills
        )

        system = (
            "你是一个任务调度器。根据用户的自然语言请求，选择要执行的技能，"
            "并提取执行所需的参数。\n\n"
            "参数提取规则：\n"
            "- call-chain 和 impact-analysis 需要 symbol 参数（函数名或类名）\n"
            "- business-rule-extraction 可选 focus 参数（一个英文单词数组，代表关注的业务域，如 ['order', 'coupon', 'pay']）\n"
            "- 其他技能不需要参数\n\n"
            "如果用户请求太模糊，无法判断要执行什么，把 clarification 设为需要用户补充的问题。\n\n"
            "输出 JSON，格式：\n"
            "{\n"
            "  \"skills\": [\"技能名\"],\n"
            "  \"params\": {\"symbol\": \"...\", \"focus\": [\"...\"]},\n"
            "  \"clarification\": null\n"
            "}\n\n"
            "只输出 JSON，不要输出任何其他内容。"
        )
        user = f"可用技能：\n{skill_list}\n\n用户请求：{user_request}"

        try:
            result = self.llm.chat_json(system, user, temperature=0.0)
        except Exception:
            return {"skills": [], "params": {}, "clarification": None}

        skill_names = result.get("skills", [])
        params = result.get("params", {}) or {}
        clarification = result.get("clarification")

        selected = []
        for name in skill_names:
            for s in skills:
                if s.name == name:
                    selected.append(s)
                    break

        return {
            "skills": selected,
            "params": params,
            "clarification": clarification,
        }


class KeywordSelector:
    """关键词匹配的 fallback 选择器。"""

    KEYWORD_MAP = {
        "project-structure": ["结构", "模块", "目录", "组织", "架构", "structure"],
        "call-chain": ["调用", "调用链", "call", "chain"],
        "impact-analysis": ["影响", "风险", "改", "impact", "risk"],
        "business-rule-extraction": ["业务", "规则", "业务逻辑", "business"],
        "dead-code-detection": ["死代码", "未使用", "冗余", "dead", "unused"],
        "dependency-cycle-detection": ["循环依赖", "循环", "环路", "cycle", "circular"],
        "business-flow-reconstruction": ["流程", "业务流程", "工作流", "flow", "process", "workflow"],
        "report-generation": ["报告", "总结", "report", "summary"],
    }

    def select_with_params(self, user_request: str, skills: List[SkillMeta]) -> dict:
        request_lower = user_request.lower()
        selected = []
        for skill in skills:
            keywords = self.KEYWORD_MAP.get(skill.name, [])
            if any(kw in request_lower for kw in keywords):
                selected.append(skill)
        return {"skills": selected, "params": {}, "clarification": None}


class Orchestrator:
    """核心调度器。"""

    def __init__(self, skills_root: str, llm: Optional[LLMClient] = None):
        self.loader = SkillLoader(skills_root)
        self.runner = SkillRunner()
        self.skills: List[SkillMeta] = []
        self.llm = llm

        if llm:
            self.selector = LLMSelector(llm)
        else:
            self.selector = KeywordSelector()

    def load_skills(self) -> List[SkillMeta]:
        self.skills = self.loader.discover()
        return self.skills

    def list_skills(self) -> List[dict]:
        if not self.skills:
            self.load_skills()
        return [
            {"name": s.name, "description": s.description,
             "depends_on": s.depends_on}
            for s in self.skills
        ]

    def select_skills(self, user_request: str) -> dict:
        return self.selector.select_with_params(user_request, self.skills)

    def resolve_dependencies(self, selected: List[SkillMeta]) -> List[SkillMeta]:
        result = []
        visited = set()
        by_name = {s.name: s for s in self.skills}

        def visit(skill: SkillMeta):
            if skill.name in visited:
                return
            visited.add(skill.name)
            for dep_name in skill.depends_on:
                dep = by_name.get(dep_name)
                if dep:
                    visit(dep)
            result.append(skill)

        for s in selected:
            visit(s)
        return result

    def execute(self, skill: SkillMeta, input_data: dict) -> Any:
        return self.runner.run(skill, input_data)

    def run(self, user_request: str, project_path: str,
            progress_callback: ProgressCallback = None) -> dict:
        if not self.skills:
            self.load_skills()

        if progress_callback:
            progress_callback("selecting", {"message": "正在理解你的需求..."})

        selection = self.select_skills(user_request)
        selected = selection.get("skills", [])
        params = selection.get("params", {}) or {}
        clarification = selection.get("clarification")

        if not selected:
            return {
                "success": False,
                "error": "no matching skill",
                "clarification": clarification,
                "available_skills": [s.name for s in self.skills],
            }

        skills_to_run = self.resolve_dependencies(selected)

        if progress_callback:
            progress_callback("resolved", {
                "requested": [s.name for s in selected],
                "executed": [s.name for s in skills_to_run],
                "params": params,
            })

        previous_results = {}
        steps = []
        skill_tokens = 0

        for skill in skills_to_run:
            if progress_callback:
                progress_callback("skill_start", {"skill": skill.name})

            input_data = {
                "project_path": os.path.abspath(project_path),
                "user_request": user_request,
                "params": params,
                "previous_results": previous_results,
            }
            result = self.execute(skill, input_data)
            steps.append({"skill": skill.name, "result": result})

            status = "unknown"
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                meta = result.get("_meta", {})
                if isinstance(meta, dict):
                    skill_tokens += meta.get("tokens", 0)
                if result.get("status") == "success":
                    previous_results[skill.name] = result.get("data", {})

            if progress_callback:
                progress_callback("skill_done", {
                    "skill": skill.name,
                    "status": status,
                })

        output = {
            "success": True,
            "steps": steps,
            "summary": {
                "requested_skills": [s.name for s in selected],
                "executed_skills": [s.name for s in skills_to_run],
                "params": params,
                "total_tokens": skill_tokens,
            },
        }

        if progress_callback:
            progress_callback("complete", {"summary": output["summary"]})

        return output