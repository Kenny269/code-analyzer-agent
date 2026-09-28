import subprocess
import json
from typing import Any, Optional
from .skill_loader import SkillMeta


class SkillRunner:
    """执行单个技能脚本。"""

    def run(self, skill: SkillMeta, input_data: dict,
            timeout: int = 120) -> Optional[Any]:
        if not skill.script_path:
            return {"error": f"skill '{skill.name}' has no entry script"}

        payload = json.dumps({"input": input_data}, ensure_ascii=False)

        try:
            result = subprocess.run(
                ["python3", skill.script_path],
                input=payload, capture_output=True, text=True,
                timeout=timeout
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip()}
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            return {"error": str(e)}