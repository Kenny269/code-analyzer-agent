import os
import json
from typing import List, Optional, Any
from .skill_loader import SkillLoader, SkillMeta
from .skill_runner import SkillRunner
from .llm_client import LLMClient


class LLMSelector:
    """用 LLM 根据用户请求选择技能。支持选择多个技能按顺序执行。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def select(self, user_request: str, skills: List[SkillMeta]) -> List[SkillMeta]:
        if not skills:
            return []
        if len(skills) == 1:
            return [skills[0]]

        skill_list = "\n".join(
            f"- {s.name}: {s.description}" for s in skills
        )

        system = (
            "你是一个任务调度器。根据用户请求，从可用技能中选择一个或多个技能。\n"
            "如果需要多个技能，按执行顺序排列，用英文逗号分隔。\n"
            "只返回技能名称，不要返回任何其他内容。\n"
            "如果没有合适的技能，返回 NONE。\n\n"
            "示例：\n"
            "用户请求：生成一份项目报告\n"
            "返回：project-structure,report-generation"
        )
        user = f"可用技能：\n{skill_list}\n\n用户请求：{user_request}\n\n请选择技能："

        try:
            chosen = self.llm.chat(system, user, temperature=0.0).strip()
        except Exception:
            return []

        if chosen.upper() == "NONE" or not chosen:
            return []

        names = [n.strip() for n in chosen.split(",") if n.strip()]
        selected = []
        for name in names:
            for s in skills:
                if s.name == name:
                    selected.append(s)
                    break
        return selected


class KeywordSelector:
    """关键词匹配的 fallback 选择器。当 LLM 不可用时使用。"""

    KEYWORD_MAP = {
        "project-structure": ["结构", "模块", "目录", "组织", "架构", "structure"],
        "call-chain": ["调用", "调用链", "call", "chain"],
        "impact-analysis": ["影响", "风险", "改", "impact", "risk"],
        "business-rule-extraction": ["业务", "规则", "业务逻辑", "business"],
        "report-generation": ["报告", "总结", "report", "summary"],
    }

    def select(self, user_request: str, skills: List[SkillMeta]) -> List[SkillMeta]:
        request_lower = user_request.lower()
        selected = []
        for skill in skills:
            keywords = self.KEYWORD_MAP.get(skill.name, [])
            if any(kw in request_lower for kw in keywords):
                selected.append(skill)
        return selected


class Orchestrator:
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

    def select_skills(self, user_request: str) -> List[SkillMeta]:
        return self.selector.select(user_request, self.skills)

    def execute(self, skill: SkillMeta, input_data: dict) -> Any:
        return self.runner.run(skill, input_data)

    def run(self, user_request: str, project_path: str) -> dict:
        if not self.skills:
            self.load_skills()

        skills_to_run = self.select_skills(user_request)
        if not skills_to_run:
            return {
                "error": "no matching skill",
                "available": [s.name for s in self.skills],
            }

        previous_results = {}
        steps = []
        skill_tokens = 0

        for skill in skills_to_run:
            input_data = {
                "project_path": os.path.abspath(project_path),
                "user_request": user_request,
                "previous_results": previous_results,
            }
            result = self.execute(skill, input_data)
            steps.append({"skill": skill.name, "result": result})

            if isinstance(result, dict):
                meta = result.get("_meta", {})
                if isinstance(meta, dict):
                    skill_tokens += meta.get("tokens", 0)
                if result.get("status") == "success":
                    previous_results[skill.name] = result.get("data", {})

        if len(steps) == 1:
            output = dict(steps[0])
        else:
            output = {"steps": steps}
        output["_meta"] = {"skill_tokens": skill_tokens}
        return output