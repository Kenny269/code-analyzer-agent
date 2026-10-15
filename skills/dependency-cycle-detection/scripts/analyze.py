#!/usr/bin/env python3
"""Dependency cycle detection skill.

Scans code files, extracts import statements, builds a dependency graph,
and finds cycles using Tarjan's strongly connected components algorithm.
"""
import sys
import json
import os
import re


SKIP_DIRS = {".git", "__pycache__", ".codegraph", "venv", ".venv",
             "node_modules", "dist", "build", "target", ".tox", ".mypy_cache",
             ".pytest_cache", "coverage", ".idea", ".vscode"}

CODE_EXTENSIONS = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
}

MAX_FILES = 500


def extract_imports_python(lines):
    imports = []
    for line in lines:
        # from X import ... / import X
        m = re.match(r"^\s*from\s+([\.\w]+)\s+import", line)
        if m:
            imports.append(m.group(1))
            continue
        m = re.match(r"^\s*import\s+([\w\.,\s]+)", line)
        if m:
            for mod in m.group(1).split(","):
                imports.append(mod.strip())
    return imports


def extract_imports_js(lines):
    imports = []
    for line in lines:
        m = re.match(r"^\s*import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", line)
        if m:
            imports.append(m.group(1))
            continue
        m = re.match(r"^\s*(?:const|let|var)\s+\w+\s*=\s*require\(['\"]([^'\"]+)['\"]\)", line)
        if m:
            imports.append(m.group(1))
    return imports


def extract_imports_java(lines):
    imports = []
    for line in lines:
        m = re.match(r"^\s*import\s+(?:static\s+)?([\w\.]+);", line)
        if m:
            imports.append(m.group(1))
    return imports


def extract_imports_generic(lines):
    imports = []
    for line in lines:
        m = re.match(r"^\s*(?:use|require|include|import)\s+['\"]?([\w\./:\-]+)", line)
        if m:
            imports.append(m.group(1))
    return imports


EXTRACTORS = {
    "python": extract_imports_python,
    "javascript": extract_imports_js,
    "typescript": extract_imports_js,
    "java": extract_imports_java,
}

# 模块名 → 项目内文件路径的匹配规则
def resolve_import(import_name, current_file, all_files_by_path, all_files_by_module):
    """把 import 的名称映射到项目内的文件路径，找不到返回 None。"""
    if not import_name:
        return None

    # 取最后一段作为模块名
    parts = re.split(r"[./]", import_name)
    if not parts:
        return None
    module_name = parts[-1]
    if not module_name:
        return None

    # 直接查表
    if module_name in all_files_by_module:
        return all_files_by_module[module_name]

    # 尝试从相对路径推断
    if import_name.startswith("."):
        base = os.path.dirname(current_file)
        resolved = os.path.normpath(os.path.join(base, import_name.replace(".", "/")))
        for suffix in (".py", ".js", ".ts", ".java"):
            candidate = resolved + suffix
            if candidate in all_files_by_path:
                return candidate

    return None


def find_cycles(graph):
    """Tarjan 算法找强连通分量。返回所有大小 >= 2 的分量。"""
    index_counter = [0]
    stack = []
    lowlink = {}
    index = {}
    on_stack = {}
    sccs = []

    def strongconnect(node):
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for neighbor in graph.get(node, []):
            if neighbor not in index:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif on_stack.get(neighbor):
                lowlink[node] = min(lowlink[node], index[neighbor])

        if lowlink[node] == index[node]:
            component = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == node:
                    break
            if len(component) > 1:
                sccs.append(component)

    for node in list(graph.keys()):
        if node not in index:
            strongconnect(node)

    return sccs


def severity_for(size):
    if size >= 5:
        return "high"
    if size >= 3:
        return "medium"
    return "low"


def main():
    payload = json.loads(sys.stdin.read())
    project_path = payload["input"]["project_path"]

    # 收集所有代码文件
    files = []
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in CODE_EXTENSIONS:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, project_path)
                files.append((rel, ext))

    total_files_scanned = len(files)
    if len(files) > MAX_FILES:
        files = files[:MAX_FILES]

    # 构建模块名索引
    all_files_by_path = {rel: rel for rel, _ in files}
    all_files_by_module = {}
    for rel, _ in files:
        mod = os.path.splitext(os.path.basename(rel))[0]
        all_files_by_module.setdefault(mod, rel)

    # 构建依赖图
    graph = {rel: set() for rel, _ in files}
    total_edges = 0

    for rel, ext in files:
        full = os.path.join(project_path, rel)
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except Exception:
            continue

        lang = CODE_EXTENSIONS.get(ext, "generic")
        extractor = EXTRACTORS.get(lang, extract_imports_generic)
        imports = extractor(lines)

        for imp in imports:
            target = resolve_import(imp, rel, all_files_by_path, all_files_by_module)
            if target and target != rel:
                graph[rel].add(target)
                total_edges += 1

    # 找环
    sccs = find_cycles(graph)

    cycles = []
    for scc in sccs:
        files_in_cycle = sorted(scc)
        cycles.append({
            "files": files_in_cycle,
            "size": len(scc),
            "severity": severity_for(len(scc)),
        })
    cycles.sort(key=lambda c: c["size"], reverse=True)

    print(json.dumps({
        "status": "success",
        "data": {
            "cycles": cycles,
            "total_cycles": len(cycles),
            "total_files_scanned": total_files_scanned,
            "total_edges": total_edges,
        },
        "error": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()