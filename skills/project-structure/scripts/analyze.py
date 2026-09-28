#!/usr/bin/env python3
"""Project structure analysis skill."""
import sys
import json
import os
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent.codegraph_client import CodeGraphClient


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]

    cg = CodeGraphClient(project_path)
    files_data = cg.files()

    if isinstance(files_data, dict) and "error" in files_data:
        print(json.dumps({"status": "error", "error": files_data["error"]}))
        return

    # 从 files 结果中提取文件列表（CodeGraph files 返回格式可能不同，做兼容）
    file_list = []
    if isinstance(files_data, list):
        file_list = files_data
    elif isinstance(files_data, dict):
        file_list = files_data.get("files", files_data.get("nodes", []))

    # 按顶层目录分组
    modules = defaultdict(list)
    for f in file_list:
        path = f if isinstance(f, str) else f.get("path", f.get("file", ""))
        if not path:
            continue
        parts = path.split(os.sep)
        module = parts[0] if len(parts) > 1 else "(root)"
        modules[module].append(path)

    # 检测构建文件
    build_files = ["pom.xml", "build.gradle", "package.json",
                   "requirements.txt", "setup.py", "Cargo.toml", "go.mod"]
    build_system = "unknown"
    for bf in build_files:
        if os.path.exists(os.path.join(project_path, bf)):
            build_system = bf
            break

    result = {
        "status": "success",
        "data": {
            "modules": [
                {"name": name, "path": name, "file_count": len(fs),
                 "files": fs[:50]}  # 只返回前 50 个文件，避免上下文过大
                for name, fs in sorted(modules.items())
            ],
            "build_system": build_system,
            "total_files": len(file_list),
        },
        "error": None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()