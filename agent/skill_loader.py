import os
import re
from dataclasses import dataclass
from typing import List


@dataclass
class SkillMeta:
    name: str
    description: str
    path: str          # 技能目录的绝对路径
    script_path: str   # 入口脚本的绝对路径


class SkillLoader:
    """扫描 skills/ 目录，发现所有技能。"""

    def __init__(self, skills_root: str):
        self.skills_root = skills_root

    def discover(self) -> List[SkillMeta]:
        skills = []
        if not os.path.isdir(self.skills_root):
            return skills

        for entry in sorted(os.listdir(self.skills_root)):
            skill_dir = os.path.join(self.skills_root, entry)
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue

            meta = self._parse_skill_md(skill_md, skill_dir)
            if meta:
                skills.append(meta)
        return skills

    def _parse_skill_md(self, path: str, skill_dir: str) -> SkillMeta:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 YAML frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        frontmatter = match.group(1)
        name = self._extract_field(frontmatter, "name")
        description = self._extract_field(frontmatter, "description")

        if not name or not description:
            return None

        # 入口脚本：scripts/ 目录下的第一个 .py 文件
        script_dir = os.path.join(skill_dir, "scripts")
        script_path = ""
        if os.path.isdir(script_dir):
            for f in sorted(os.listdir(script_dir)):
                if f.endswith(".py"):
                    script_path = os.path.join(script_dir, f)
                    break

        return SkillMeta(
            name=name,
            description=description,
            path=skill_dir,
            script_path=script_path,
        )

    @staticmethod
    def _extract_field(frontmatter: str, field: str) -> str:
        # 简单解析 YAML 字段，支持单行和多行
        pattern = rf"^{field}:\s*(.+?)(?=\n\w+:|\Z)"
        match = re.search(pattern, frontmatter, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        return ""