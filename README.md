# Code Analyzer Agent

一个面向遗留系统的智能代码分析 Agent。既能给技术人员看代码结构，也能给业务人员看业务逻辑。

支持三种调用方式：**命令行**、**Web 界面**、**MCP 协议**（可接入 Cursor / VS Code / Claude Code 等 AI IDE）。

---

## 项目简介

这个项目用 LLM + CodeGraph + 可组合技能的方式，对代码库进行结构化分析。核心能力包括：

- **代码结构分析**：识别模块划分、目录组织、构建系统
- **调用链分析**：查询某个函数的调用者和被调用者
- **影响分析**：评估修改某个符号会影响哪些代码
- **业务规则抽取**：从代码中提取业务人员能看懂的自然语言规则（支持意图聚焦与智能打分）
- **业务流程重建**：从代码还原端到端的业务流程
- **死代码检测**：识别疑似未使用的函数和类（辅助人工复核）
- **循环依赖检测**：发现模块间的循环依赖，识别重构阻塞点
- **报告生成**：把分析结果转成可读的中文报告

所有分析结果以结构化 JSON 输出，可直接保存、导出为 Markdown，或接入后续流程。

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
│  - 意图理解：解析自然语言，提取技能与参数（如 symbol, focus） │
│  - 展开技能依赖（depends_on），做拓扑排序                     │
│  - 按顺序执行技能，串联上下文                                 │
│  - 通过 progress_callback 上报进度                           │
│  - 汇总 token 消耗并返回结构化 dict                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  技能执行层                                                  │
│  skill_loader.py  │  skill_runner.py                        │
│  - 扫描 skills/ 目录                                        │
│  - 解析 SKILL.md 元数据（含 depends_on）                     │
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
│  - business-rule-extraction（焦点驱动 + 智能打分）           │
│  - business-flow-reconstruction                             │
│  - dead-code-detection                                      │
│  - dependency-cycle-detection                               │
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

### 模块耦合与智能调度

**意图理解与参数提取**：
`orchestrator.py` 中的 `LLMSelector` 不再只负责选技能，还会从自然语言中提取执行参数。例如，用户输入“提取订单、优惠券相关的业务规则”，LLM 会输出 `{"skills": ["business-rule-extraction"], "params": {"focus": ["order", "coupon"]}}`。

**焦点驱动的业务规则抽取**：
`business-rule-extraction` 抛弃了盲目遍历全库的低效做法，引入了智能打分与配额机制：
1. **目录排雷**：强制跳过前端目录（`frontend`, `admin`, `vue`等）、测试目录和依赖库。
2. **权重打分**：文件路径命中 `focus` 关键词加 100 分，位于 `service/biz/domain` 核心层加 50 分，工具类（`util`, `config`）降权。
3. **防垄断配额**：按得分扫描前 120 个文件，并限制单一巨型文件（如 2000 行的 `OrderServiceImpl`）最多只能贡献 10 个候选点，确保跨模块业务规则不被淹没。

**SSE 进度反馈与防死锁**：
Web 端使用 `ThreadingHTTPServer` 和 `Server-Sent Events (SSE)` 推送进度。前端收到 `complete` 或 `error` 事件时，主动调用 `reader.cancel()` 断开底层长连接，并在 `finally` 块中恢复按钮状态，彻底解决长时间分析导致的 UI 挂起和按钮变灰问题。

### 数据流

```
用户请求 + 项目路径
   │
   ▼
Orchestrator.run(progress_callback)
   │
   ├─→ Selector.select()         意图理解与参数提取
   ├─→ resolve_dependencies()    展开依赖，拓扑排序
   │
   ├─→ 对每个技能（含依赖）：
   │     │
   │     ├─→ progress_callback("skill_start", {skill})
   │     ├─→ SkillRunner.run()  启动子进程
   │     │     │
   │     │     ├─→ 技能脚本读取 stdin JSON
   │     │     ├─→ 读取 previous_results
   │     │     ├─→ 查询 CodeGraph / LLM
   │     │     └─→ 输出 stdout JSON
   │     │
   │     ├─→ progress_callback("skill_done", {skill, status})
   │     └─→ 收集结果，传给下一个技能
   │
   └─→ progress_callback("complete", {summary})
```

---

## 目录结构

```
code_analyzing_agent/
├── main.py                          # CLI 入口
├── server.py                        # Web 入口（含 SSE 进度流）
├── mcp_server.py                    # MCP 入口（IDE 集成）
├── .env                             # 配置（不提交）
├── .env.example                     # 配置模板
├── .gitignore
├── README.md
├── Plan.md                          # 项目规划文档
├── agent/
│   ├── __init__.py
│   ├── orchestrator.py              # 编排器 + 意图提取 + 依赖解析
│   ├── skill_loader.py              # 技能发现与元数据解析
│   ├── skill_runner.py              # 技能执行引擎
│   ├── codegraph_client.py          # CodeGraph CLI 封装
│   └── llm_client.py                # LLM 调用封装
├── skills/
│   ├── project-structure/
│   ├── call-chain/
│   ├── impact-analysis/
│   ├── business-rule-extraction/    # 焦点驱动与智能打分
│   ├── business-flow-reconstruction/
│   ├── dead-code-detection/
│   ├── dependency-cycle-detection/
│   └── report-generation/
├── static/
│   ├── index.html                   # Web 前端页面
│   ├── style.css
│   └── app.js
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
python3 main.py /path/to/project "分析项目结构"
python3 main.py /path/to/project "提取订单和优惠券的业务规则"
python3 main.py /path/to/project "重建下单到支付的业务流程"
python3 main.py /path/to/project "检测死代码"
python3 main.py /path/to/project "分析 create_task 的调用链"
```

### 方式二：Web 界面

启动服务：

```bash
cd code_analyzing_agent
python3 server.py
```

浏览器打开 `http://127.0.0.1:8080`。

界面交互：

- **项目路径**：点击「选择文件夹」按钮弹出系统原生对话框，或直接粘贴 Git URL。
- **自由输入**：像聊天一样描述需求（如“看看订单模块的规则”），系统自动提取意图和参数。
- **快捷示例**：点击下方的 Chip 快速填入常见请求。
- **精确模式**：展开高级选项，手动指定技能。
- **实时进度**：页面实时显示克隆、索引、执行的进度步骤，且不会卡死按钮。
- **导出报告**：分析完成后，一键下载 Markdown 文件。
- **分析历史**：底部分析历史（localStorage），点击任意一条即可秒载结果，无需重跑。

分析结果按技能类型分别可视化：

| 技能 | 可视化形式 |
|------|-----------|
| 项目结构 | 模块卡片列表，显示文件数与文件清单 |
| 业务规则 | 按业务能力分组，显示规则描述、分类、代码位置 |
| 业务流程 | 流程卡片，含有序步骤列表和业务总结 |
| 死代码 | 表格 + 置信度徽章 + 复核建议 |
| 循环依赖 | 循环卡片列表，标注严重程度和涉及文件 |
| 调用链 | 调用者 / 被调用者分组列表 |
| 影响分析 | 彩色风险横幅 + 受影响符号表格 |
| 报告生成 | Markdown 渲染为 HTML |

### 方式三：MCP 协议（IDE 集成）

MCP Server 通过 stdio 传输暴露工具：

- `analyze_project(project_path, request)`：执行分析，返回 JSON
- `list_skills()`：返回可用技能列表

在 Cursor 或 VS Code 的 `mcp.json` 中配置：
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

---

## 现有技能

| 技能 | 用途 | 依赖 |
|------|------|------|
| `project-structure` | 分析模块划分、目录结构 | CodeGraph |
| `call-chain` | 查询符号的调用者和被调用者 | CodeGraph |
| `impact-analysis` | 评估修改某个符号的影响范围 | CodeGraph |
| `business-rule-extraction` | 抽取业务规则（支持 focus 聚焦） | CodeGraph + LLM |
| `business-flow-reconstruction` | 重建端到端业务流程 | project-structure + business-rule-extraction |
| `dead-code-detection` | 检测疑似死代码（需人工复核） | CodeGraph |
| `dependency-cycle-detection` | 检测模块间的循环依赖 | 无（纯文件扫描 + Tarjan 算法） |
| `report-generation` | 把结果转成可读报告 | LLM |

### 技能依赖与输出格式

技能可以在 `SKILL.md` 的 frontmatter 里声明 `depends_on`。编排器会自动拓扑排序。所有技能统一遵循以下输出协议：

```json
{
  "status": "success",
  "data": { ... },
  "error": null,
  "_meta": { "tokens": 1234 }
}
```

编排器汇总后的输出：

```json
{
  "success": true,
  "steps": [
    { "skill": "project-structure", "result": { ... } }
  ],
  "summary": {
    "requested_skills": ["business-rule-extraction"],
    "executed_skills": ["business-rule-extraction"],
    "params": {"focus": ["order", "coupon"]},
    "total_tokens": 1554
  }
}
```

---

## 更新记录

- **v0.1**（2026-09-24）：单脚本 Demo，逐文件摘要 + 汇总报告。
- **v0.2**（2026-09-28）：Skill 化改造，接入 CodeGraph，5 个技能，LLM 语义选择，Web 界面。
- **v0.3**（2026-09-29）：MCP Server，IDE 集成，orchestrator 返回结构化 dict，前端技能列表。
- **v0.4**（2026-09-30）：业务流程重建技能，死代码检测技能，Skill 依赖机制（depends_on），前端多类型可视化，文件夹选择对话框，下拉选择分析类型，导出 Markdown 报告。
- **v0.5**（2026-10-15）：循环依赖检测技能，SSE 实时进度反馈，分析历史记录（localStorage），ThreadingHTTPServer 并发支持，技能中文标签。
- **v0.6**（2026-10-21）：**自然语言意图提取与参数解析（focus/symbol），焦点驱动的业务规则抽取（目录排雷与智能打分防垄断），修复 SSE 长连接导致的 UI 按钮死锁**。
- **v0.7**（2026-10-26）：**新增业务能力全景技能（快速摸清系统架构），后端引入拓扑分层并发执行引擎（大幅缩短多技能分析时间），修复 SSE 异常捕获与 UI 卡死问题**。
---

## 后续计划

- 引入“业务文档”输入接口，与代码规则进行交叉验证。
- 在真实的 1000+ 文件大型项目（如电商系统）上验证全量业务流程重建。
- 引入本体（Ontology）构建，把分析结果沉淀为图数据库，支持增量分析。
- 增加更多技能：技术债务量化、API 清单生成、敏感信息扫描。

---

*本 README 随项目推进持续更新，每次更新仅在“更新记录”追加。*
