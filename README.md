# Code Analyzer Agent

一个面向遗留系统的智能代码分析 Agent。既能给技术人员看代码结构，也能给业务人员看业务逻辑。

支持三种调用方式：**命令行**、**Web 界面**、**MCP 协议**（可接入 Cursor / VS Code / Claude Code 等 AI IDE）。

---

## 项目简介

这个项目用 LLM + CodeGraph + 可组合技能的方式，对代码库进行结构化分析。核心能力包括：

- **代码结构分析**：识别模块划分、目录组织、构建系统
- **调用链分析**：查询某个函数的调用者和被调用者
- **影响分析**：评估修改某个符号会影响哪些代码
- **业务规则抽取**：从代码中提取业务人员能看懂的自然语言规则
- **报告生成**：把分析结果转成可读的中文报告

所有分析结果以结构化 JSON 输出，可直接保存或接入后续流程。

---

## 核心设计

### 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  入口层                                                      │
│  main.py (CLI)  │  server.py (Web)  │  mcp_server.py (MCP)  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  编排层                                                      │
│  orchestrator.py                                            │
│  - 加载所有技能                                              │
│  - 根据用户请求选择技能（LLM 语义匹配 / 关键词回退）           │
│  - 按顺序执行技能，串联上下文                                 │
│  - 汇总 token 消耗                                          │
│  - 返回结构化 dict（不再直接打印 JSON）                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  技能执行层                                                  │
│  skill_loader.py  │  skill_runner.py                        │
│  - 扫描 skills/ 目录                                        │
│  - 解析 SKILL.md 元数据                                     │
│  - 以子进程执行技能脚本                                      │
│  - 通过 stdin/stdout JSON 通信                              │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  技能层 skills/                                              │
│  每个技能是独立目录，包含 SKILL.md + scripts/                 │
│  - project-structure                                        │
│  - call-chain                                               │
│  - impact-analysis                                          │
│  - business-rule-extraction                                 │
│  - report-generation                                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  共享工具层                                                  │
│  codegraph_client.py  │  llm_client.py                      │
│  - CodeGraph CLI 封装（代码图查询）                          │
│  - LLM 调用封装（DeepSeek / OpenAI 兼容）                    │
└─────────────────────────────────────────────────────────────┘
```

### 模块耦合关系

**入口层**负责接收用户输入，不做业务逻辑，只是把 `project_path` + `user_request` 传给编排器。

- `main.py`：解析命令行参数
- `server.py`：解析 HTTP 请求，提供 Web 界面和 REST API
- `mcp_server.py`：实现 MCP 协议，把能力暴露为 MCP 工具，供 AI IDE 调用

三个入口共用同一个 `Orchestrator` 实例。

**编排层**是系统的核心调度中心。它启动时通过 `skill_loader` 扫描 `skills/` 目录，把所有技能的元数据（`name` + `description`）读入内存。用户请求到来时，通过 LLM 语义匹配选出最相关的技能（一个或多个）。如果 LLM 不可用，则回退到关键词匹配。

`orchestrator.run()` 返回结构化的 dict：

```python
{
  "success": True,
  "steps": {"skill": "...", "result": {...}} 或 [ {...}, {...} ],
  "summary": {"skills_run": [...], "total_tokens": 1234}
}
```

**技能执行层**以子进程方式运行技能脚本。每个技能脚本从 `stdin` 读 JSON，向 `stdout` 写 JSON。这样做的好处是技能之间完全隔离，任何技能崩溃都不会影响编排器，且技能可以用任意语言实现。技能脚本输出中的 `_meta.tokens` 字段会被编排器收集，用于汇总 token 消耗。

**技能层**是能力的具体实现。每个技能是一个独立目录，包含 `SKILL.md`（元数据 + 执行说明）和 `scripts/`（实现代码）。新增技能不需要改任何核心代码，只需在 `skills/` 下新建目录。技能之间的数据传递通过 `previous_results` 字段：前一个技能的 `data` 会被塞入下一个技能的输入。

**共享工具层**提供两个基础能力：`codegraph_client` 封装所有 CodeGraph CLI 调用，是所有代码结构信息的唯一来源；`llm_client` 封装所有 LLM 调用，处理重试、超时、token 计数。这两层被技能层和编排层共用。替换 CodeGraph 为 MCP 只需改 `codegraph_client.py`，替换 LLM 服务商只需改 `.env`。

### 数据流

```
用户请求 + 项目路径
   │
   ▼
Orchestrator.run()
   │
   ├─→ LLMSelector.select()  选择技能
   │
   ├─→ 对每个技能：
   │     │
   │     ├─→ SkillRunner.run()  启动子进程
   │     │     │
   │     │     ├─→ 技能脚本读取 stdin JSON
   │     │     ├─→ 查询 CodeGraph（如需要）
   │     │     ├─→ 调用 LLM（如需要）
   │     │     └─→ 输出 stdout JSON
   │     │
   │     └─→ 收集结果，传给下一个技能
   │
   └─→ 返回汇总结果 + token 统计
```

---

## 目录结构

```
code_analyzing_agent/
├── main.py                          # CLI 入口
├── server.py                        # Web 入口
├── mcp_server.py                    # MCP 入口（IDE 集成）
├── .env                             # 配置（不提交）
├── .env.example                     # 配置模板
├── .gitignore
├── README.md
├── Plan.md                          # 项目规划文档
├── agent/
│   ├── __init__.py
│   ├── orchestrator.py              # 编排器 + 技能选择
│   ├── skill_loader.py              # 技能发现与元数据解析
│   ├── skill_runner.py              # 技能执行引擎
│   ├── codegraph_client.py          # CodeGraph CLI 封装
│   └── llm_client.py                # LLM 调用封装
├── skills/
│   ├── project-structure/
│   │   ├── SKILL.md
│   │   └── scripts/analyze.py
│   ├── call-chain/
│   │   ├── SKILL.md
│   │   └── scripts/analyze.py
│   ├── impact-analysis/
│   │   ├── SKILL.md
│   │   └── scripts/analyze.py
│   ├── business-rule-extraction/
│   │   ├── SKILL.md
│   │   └── scripts/analyze.py
│   └── report-generation/
│       ├── SKILL.md
│       └── scripts/analyze.py
├── static/
│   ├── index.html                   # Web 前端页面
│   ├── style.css
│   └── app.js
├── .cursor/
│   └── mcp.json                     # Cursor MCP 配置（不提交）
└── .vscode/
    └── mcp.json                     # VS Code MCP 配置（不提交）
```

---

## 前置依赖

- Python 3.10+
- CodeGraph（`codegraph` 命令在 PATH 中可用）
- Git（如果分析 Git 仓库）
- DeepSeek API Key（或任何 OpenAI 兼容的模型服务）
- Node.js（可选，用于运行 MCP Inspector 调试工具）

安装 Python 依赖：

```bash
pip3 install openai python-dotenv "mcp[cli]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

安装 CodeGraph：

```bash
npm i -g @colbymchenry/codegraph
codegraph --version
```

---

## 配置

复制 `.env.example` 为 `.env`，填入你的配置：

```
LLM_API_KEY=sk-你的Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
```

如果 `.env` 不存在或 LLM 配置无效，系统会自动回退到关键词匹配模式，基础功能仍可用。

---

## 使用方式

### 方式一：命令行

```bash
cd code_analyzing_agent
python3 main.py <项目路径> "<分析请求>"
```

示例：

```bash
# 项目结构分析
python3 main.py /path/to/project "分析项目结构"

# 业务规则抽取
python3 main.py /path/to/project "提取这个系统的业务规则"

# 调用链分析
python3 main.py /path/to/project "分析 create_task 的调用链"

# 影响分析
python3 main.py /path/to/project "改动 create_task 的影响"

# 多技能链式调用
python3 main.py /path/to/project "生成一份项目报告"
```

### 方式二：Web 界面

启动服务：

```bash
cd code_analyzing_agent
python3 server.py
```

浏览器打开：

```
http://127.0.0.1:8080
```

在页面上填写：

- **项目路径**：本地绝对路径（如 `/Users/xxx/project`）或 Git URL（如 `https://github.com/user/repo`）
- **分析请求**：自然语言描述，如「提取这个系统的业务规则」
- **报告保存位置**：留空则默认保存在被分析项目目录下

点击「开始分析」，等待结果。

如果传入的是 Git URL，后端会自动 clone 到临时目录，分析完成后自动清理。如果项目没有 `.codegraph` 索引，后端会自动执行 `codegraph init -i`。

### 方式三：MCP 协议（IDE 集成）

MCP Server 通过 stdio 传输暴露两个工具：

- `analyze_project(project_path, request)`：执行分析，返回 JSON
- `list_skills()`：返回可用技能列表

#### 用 MCP Inspector 调试

```bash
mcp dev mcp_server.py
```

浏览器打开 `http://localhost:3000`，配置 Command 为 `python3`，Arguments 为 `mcp_server.py` 的绝对路径，点 Connect，然后测试工具。

#### 接入 Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "code-analyzer": {
      "command": "python3",
      "args": ["/abs/path/to/mcp_server.py"]
    }
  }
}
```

打开 Cursor，它会自动读取该配置。在 Chat 里输入「用 code-analyzer 分析 Py_test 项目结构」即可。

#### 接入 VS Code

在项目根目录创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "code-analyzer": {
      "type": "stdio",
      "command": "python3",
      "args": ["/abs/path/to/mcp_server.py"]
    }
  }
}
```

需要安装 GitHub Copilot 插件。MCP 工具会自动出现在 Copilot Chat 的工具列表中。

#### 接入 Claude Code

```bash
claude mcp add code-analyzer python3 /abs/path/to/mcp_server.py
```

之后在对话里说「用 code-analyzer 分析一下这个项目」即可。

---

## 现有技能

| 技能 | 用途 | 依赖 |
|------|------|------|
| `project-structure` | 分析模块划分、目录结构、构建系统 | CodeGraph |
| `call-chain` | 查询指定符号的调用者和被调用者 | CodeGraph |
| `impact-analysis` | 评估修改某个符号的影响范围 | CodeGraph |
| `business-rule-extraction` | 从代码中抽取业务规则（自然语言） | CodeGraph + LLM |
| `report-generation` | 把分析结果转成可读报告 | LLM |

### 如何新增一个技能

1. 在 `skills/` 下创建新目录，例如 `skills/my-skill/`
2. 创建 `SKILL.md`，写入 YAML frontmatter：

```markdown
---
name: my-skill
description: 这个技能做什么，什么时候使用。描述要包含触发关键词。
---

# My Skill

## Steps
1. ...
2. ...

## Output Format
返回 JSON，包含 ...
```

3. 创建 `scripts/analyze.py`，从 `stdin` 读 JSON，向 `stdout` 写 JSON：

```python
import sys
import json

payload = json.loads(sys.stdin.read())
project_path = payload["input"]["project_path"]
# ... 你的逻辑 ...
print(json.dumps({"status": "success", "data": {...}, "error": None}, ensure_ascii=False))
```

不需要改任何核心代码，`skill_loader` 会自动发现新技能。

---

## 输出格式

### 技能输出协议

```json
{
  "status": "success",
  "data": { ... },
  "error": null,
  "_meta": { "tokens": 1234 }
}
```

- `status`：`success` 或 `error`
- `data`：技能的具体输出
- `error`：错误信息（成功时为 `null`）
- `_meta.tokens`：该技能消耗的 LLM token 数（用于汇总）

### 编排器输出结构

```json
{
  "success": true,
  "steps": { "skill": "...", "result": { ... } },
  "summary": { "skills_run": [...], "total_tokens": 1234 }
}
```

多技能链式调用时，`steps` 变为数组：

```json
{
  "success": true,
  "steps": [
    { "skill": "project-structure", "result": { ... } },
    { "skill": "report-generation", "result": { ... } }
  ],
  "summary": { "skills_run": [...], "total_tokens": 1234 }
}
```

---

## 兼容性

- Mac / Windows 均兼容
- 路径处理使用 `os.path`，不做硬编码
- Web 服务使用 Python 标准库 `http.server`，无额外框架依赖
- MCP Server 使用官方 `mcp` SDK
- 前端无框架，原生 HTML + CSS + JS

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `codegraph: command not found` | CodeGraph 未安装或未在 PATH | `npm i -g @colbymchenry/codegraph`，或参考官方安装文档 |
| LLM disabled | `.env` 未配置或 Key 无效 | 检查 `.env` 文件，确认 `LLM_API_KEY` 正确 |
| 分析结果为空 | 项目未建 CodeGraph 索引 | 进入项目目录执行 `codegraph init -i` |
| 报告保存失败 | 目标目录无写权限 | 在 Web 界面指定一个有写权限的目录 |
| 浏览器打不开 | 端口被占用 | `PORT=8090 python3 server.py` |
| Git clone 超时 | 网络问题或仓库太大 | 换用本地路径，或增大 `server.py` 中的 timeout |
| MCP Inspector 连接失败 | Command / Arguments 填错 | Command 只填 `python3`，路径填到 Arguments 里 |
| npm 缓存报 EEXIST | npm 缓存损坏 | `npm cache clean --force`，必要时删 `~/.npm/_cacache` |

---

## 更新记录

- **v0.1**（2026-09-24）：单脚本 Demo，逐文件摘要 + 汇总报告
- **v0.2**（2026-09-28）：Skill 化改造，接入 CodeGraph，5 个技能，LLM 语义选择，Web 界面
- **v0.3**（2026-09-29）：MCP Server，IDE 集成，orchestrator 返回结构化 dict，前端技能列表

---

## 后续计划

- 增加更多技能：死代码检测、数据流分析、技术债务量化
- 输出结构化格式（JSON-LD / OWL），为写入本体做准备
- 接入多智能体协作，支持并行分析和交叉验证
- 增加增量分析，代码变更后只更新受影响部分
- 完善链式调用，支持技能依赖声明和并行执行

---

*本 README 随项目推进持续更新。*