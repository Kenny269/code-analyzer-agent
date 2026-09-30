import os
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class SkillMeta:
    name: str
    description: str
    path: str          # 技能目录的绝对路径
    script_path: str   # 入口脚本的绝对路径
    depends_on: List[str] = field(default_factory=list)


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

        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        frontmatter = match.group(1)
        name = self._extract_field(frontmatter, "name")
        description = self._extract_field(frontmatter, "description")
        depends_on = self._extract_list_field(frontmatter, "depends_on")

        if not name or not description:
            return None

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
            depends_on=depends_on,
        )

    @staticmethod
    def _extract_field(frontmatter: str, field: str) -> str:
        pattern = rf"^{field}:\s*(.+?)(?=\n\w+:|\Z)"
        match = re.search(pattern, frontmatter, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        return ""

    @staticmethod
    def _extract_list_field(frontmatter: str, field: str) -> List[str]:
        """解析 YAML 列表字段，支持两种格式：
        depends_on:
          - skill-a
          - skill-b
        或
        depends_on: [skill-a, skill-b]
        """
        # 行内格式
        inline = re.search(rf"^{field}:\s*\[(.*?)\]", frontmatter, re.MULTILINE)
        if inline:
            return [s.strip().strip('"').strip("'")
                    for s in inline.group(1).split(",") if s.strip()]

        # 块格式
        block = re.search(
            rf"^{field}:\s*\n((?:\s+-\s+.+\n?)+)",
            frontmatter, re.MULTILINE
        )
        if block:
            items = re.findall(r"-\s+(.+)", block.group(1))
            return [s.strip().strip('"').strip("'") for s in items if s.strip()]

        return []