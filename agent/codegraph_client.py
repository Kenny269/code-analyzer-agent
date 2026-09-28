import subprocess
import json
from typing import Optional, Any


class CodeGraphClient:
    """CodeGraph CLI 的统一封装。所有技能通过它查询代码图。"""

    def __init__(self, project_path: str):
        self.project_path = project_path

    def _run(self, args: list) -> Optional[Any]:
        """执行 codegraph 命令，返回解析后的 JSON。"""
        cmd = ["codegraph"] + args + ["-j"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=self.project_path, timeout=60
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip()}
            output = result.stdout.strip()
            if not output:
                return []
            return json.loads(output)
        except subprocess.TimeoutExpired:
            return {"error": "codegraph command timed out"}
        except json.JSONDecodeError as e:
            return {"error": f"failed to parse codegraph output: {e}"}
        except FileNotFoundError:
            return {"error": "codegraph command not found. Is it installed and on PATH?"}

    def query(self, keyword: str, limit: int = 10):
        """搜索符号。返回 CodeGraph 原始结果（可能是 list 或 dict）。"""
        return self._run(["query", keyword, "--limit", str(limit)])

    def callers(self, symbol: str):
        """查询调用者。"""
        return self._run(["callers", symbol])

    def callees(self, symbol: str):
        """查询被调用者。"""
        return self._run(["callees", symbol])

    def impact(self, symbol: str, depth: int = 2):
        """影响分析。"""
        return self._run(["impact", symbol, "--depth", str(depth)])

    def files(self):
        """项目文件结构。"""
        return self._run(["files"])

    def status(self):
        """索引状态。"""
        return self._run(["status"])