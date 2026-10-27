import os
import json
import concurrent.futures
from typing import List, Optional, Any, Callable
from .skill_loader import SkillLoader, SkillMeta
from .skill_runner import SkillRunner
from .llm_client import LLMClient

ProgressCallback = Optional[Callable[[str, dict], None]]

class LLMSelector:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def select_with_params(self, user_request: str, skills: List[SkillMeta], has_business_doc: bool) -> dict:
        if not skills:
            return {"skills": [], "params": {}, "clarification": None}
        
        # 如果只有1个技能，或者用户带了文档并且只想要规则提取
        if len(skills) == 1:
            return {"skills": [skills[0]], "params": {}, "clarification": None}

        skill_list = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        
        doc_hint = "注意：用户提供了业务文档/背景，请优先选择 `business-rule-extraction` 技能进行代码与文档的交叉验证。\n" if has_business_doc else ""

        system = (
            "你是一个任务调度器。根据用户的自然语言请求，选择要执行的技能，并提取参数。\n"
            f"{doc_hint}"
            "参数提取规则：\n"
            "- call-chain 和 impact-analysis 需要 symbol 参数\n"
            "- business-rule-extraction 可选 focus 参数（英文数组，如 ['order', 'coupon']）\n"
            "- 其他技能不需要参数\n\n"
            "输出 JSON：\n"
            "{\n"
            "  \"skills\": [\"技能名\"],\n"
            "  \"params\": {\"symbol\": \"...\", \"focus\": [\"...\"]},\n"
            "  \"clarification\": null\n"
            "}"
        )
        user = f"可用技能：\n{skill_list}\n\n用户请求：{user_request}"

        try:
            result = self.llm.chat_json(system, user, temperature=0.0)
            skill_names = result.get("skills", [])
            params = result.get("params", {}) or {}
            clarification = result.get("clarification")
            
            # 如果用户提供了文档，但没选规则提取，强行加上（业务审计的核心）
            if has_business_doc and "business-rule-extraction" not in skill_names:
                skill_names.append("business-rule-extraction")

            selected = [s for name in skill_names for s in skills if s.name == name]
            return {"skills": selected, "params": params, "clarification": clarification}
        except Exception:
            return {"skills": [], "params": {}, "clarification": None}

class KeywordSelector:
    KEYWORD_MAP = {
        "project-structure": ["结构", "模块", "目录"],
        "call-chain": ["调用", "调用链"],
        "impact-analysis": ["影响", "风险", "改"],
        "business-rule-extraction": ["业务", "规则", "审计", "交叉", "文档"],
        "dead-code-detection": ["死代码", "未使用"],
        "dependency-cycle-detection": ["循环依赖", "循环"],
        "business-flow-reconstruction": ["流程", "业务流程", "工作流"],
        "business-capability-map": ["全景", "业务能力", "系统概览"],
        "report-generation": ["报告", "总结"],
    }

    def select_with_params(self, user_request: str, skills: List[SkillMeta], has_business_doc: bool) -> dict:
        request_lower = user_request.lower()
        selected = []
        for skill in skills:
            keywords = self.KEYWORD_MAP.get(skill.name, [])
            if any(kw in request_lower for kw in keywords):
                selected.append(skill)
        return {"skills": selected, "params": {}, "clarification": None}

class Orchestrator:
    def __init__(self, skills_root: str, llm: Optional[LLMClient] = None):
        self.loader = SkillLoader(skills_root)
        self.runner = SkillRunner()
        self.skills: List[SkillMeta] = []
        self.llm = llm
        self.selector = LLMSelector(llm) if llm else KeywordSelector()

    def load_skills(self) -> List[SkillMeta]:
        self.skills = self.loader.discover()
        return self.skills

    def list_skills(self) -> List[dict]:
        if not self.skills:
            self.load_skills()
        return [{"name": s.name, "description": s.description, "depends_on": s.depends_on} for s in self.skills]

    def select_skills(self, user_request: str, has_business_doc: bool) -> dict:
        return self.selector.select_with_params(user_request, self.skills, has_business_doc)

    def resolve_dependencies_to_levels(self, selected: List[SkillMeta]) -> List[List[SkillMeta]]:
        visited = {}
        by_name = {s.name: s for s in self.skills}
        
        def get_level(skill):
            if skill.name in visited: return visited[skill.name]
            max_dep_level = -1
            for dep_name in skill.depends_on:
                dep = by_name.get(dep_name)
                if dep: max_dep_level = max(max_dep_level, get_level(dep))
            level = max_dep_level + 1
            visited[skill.name] = level
            return level

        levels_dict = {}
        for s in selected:
            lvl = get_level(s)
            levels_dict.setdefault(lvl, []).append(s)
        return [levels_dict[lvl] for lvl in sorted(levels_dict.keys())]

    def execute_skill(self, skill: SkillMeta, user_request: str, project_path: str, params: dict, previous_results: dict, business_doc: str) -> tuple:
        try:
            input_data = {
                "project_path": os.path.abspath(project_path),
                "user_request": user_request,
                "params": params,
                "previous_results": previous_results,
                "business_doc": business_doc, # 传递给技能
            }
            result = self.runner.run(skill, input_data)
            return skill, result
        except Exception as e:
            return skill, {"status": "error", "error": f"Internal Error: {str(e)}"}

    def run(self, user_request: str, project_path: str, business_doc: str = "", progress_callback: ProgressCallback = None) -> dict:
        if not self.skills:
            self.load_skills()

        if progress_callback:
            progress_callback("selecting", {"message": "正在理解需求..."})

        selection = self.select_skills(user_request, bool(business_doc))
        selected = selection.get("skills", [])
        params = selection.get("params", {}) or {}
        clarification = selection.get("clarification")

        if not selected:
            return {"success": False, "error": "no matching skill", "clarification": clarification or "无法理解请求"}

        levels = self.resolve_dependencies_to_levels(selected)
        all_executed_names = [s.name for lvl in levels for s in lvl]

        if progress_callback:
            progress_callback("resolved", {
                "requested": [s.name for s in selected],
                "executed": all_executed_names,
                "params": params,
            })

        previous_results = {}
        steps = []
        skill_tokens = 0

        for level_idx, level_skills in enumerate(levels):
            if progress_callback:
                for s in level_skills:
                    progress_callback("skill_start", {"skill": s.name})

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self.execute_skill, s, user_request, project_path, params, previous_results, business_doc): s
                    for s in level_skills
                }
                
                for future in concurrent.futures.as_completed(futures):
                    try:
                        skill, result = future.result()
                    except Exception as e:
                        skill = futures[future]
                        result = {"status": "error", "error": str(e)}
                    
                    status = result.get("status", "unknown")
                    if isinstance(result.get("_meta"), dict):
                        skill_tokens += result["_meta"].get("tokens", 0)
                    if status == "success":
                        previous_results[skill.name] = result.get("data", {})
                    
                    steps.append({"skill": skill.name, "result": result})
                    if progress_callback:
                        progress_callback("skill_done", {"skill": skill.name, "status": status})

        steps.sort(key=lambda x: all_executed_names.index(x["skill"]))

        output = {
            "success": True,
            "steps": steps,
            "summary": {
                "requested_skills": [s.name for s in selected],
                "executed_skills": all_executed_names,
                "params": params,
                "total_tokens": skill_tokens,
            },
        }

        if progress_callback:
            progress_callback("complete", {"summary": output["summary"]})

        return output