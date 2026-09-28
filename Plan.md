

---

# 遗留系统智能分析 Agent — 项目指引

> 版本：v0.1  
> 创建日期：2026-09-23  
> 目标：从单文件分析 Demo 演进为可处理大型项目、具备技能体系、支持业务逻辑抽取、有用户界面的开源 Agent 项目

---

## 1. 项目定位

**一句话描述**：一个基于代码知识图谱和 LLM 的遗留系统分析 Agent，既能给技术人员看代码结构，也能给业务人员看业务逻辑。

**核心差异点**：
- 不是简单的“大模型读代码”，而是有明确技能边界、可组合、可复用的 Agent 系统
- 用 CodeGraph 解决大项目上下文爆炸问题
- 业务规则抽取作为独立技能，输出面向业务人员的自然语言描述
- 最终提供 Web 界面和 IDE 接入能力

**当前状态**：已完成单脚本 Demo，能分析几十个文件的小项目，输出 Markdown 报告。

**下一阶段目标**：完成 Skill 化改造，接入 CodeGraph，增加业务分析技能，搭建最小前端。

---

## 2. 总体路线图

三周为核心周期，第四周为可选的前端和开源准备。

| 阶段 | 时间 | 核心任务 | 交付物 |
|------|------|----------|--------|
| 第一周 | Day 1-5 | Skill 化改造 | 两个基础 Skill + 技能调度器 |
| 第二周 | Day 1-5 | 深化技能 + 业务分析 | 依赖分析 Skill + 业务规则抽取 Skill |
| 第三周 | Day 1-5 | 接入 CodeGraph | 图驱动的大项目分析能力 |
| 第四周（可选） | Day 1-5 | 前端 + 开源准备 | HTML 页面 + GitHub 仓库 |

**裁剪原则**：如果时间紧张，优先保证第一周和第二周。CodeGraph 和前端可以延后，但 Skill 化和业务分析是核心价值。

---

## 3. 核心概念

### 3.1 Agent Skill 是什么

Skill 是一组有明确输入输出、有执行流程、有质量标准的任务单元。它和普通工具函数的区别：

| 维度 | 工具（Tool） | 技能（Skill） |
|------|-------------|---------------|
| 粒度 | 单个函数调用 | 完整任务闭环 |
| 输入输出 | 参数 → 返回值 | 结构化输入 → 结构化输出 |
| 执行流程 | 无 | 多步骤，可能调用多个工具 |
| 质量标准 | 无 | 有验收标准 |
| 复用方式 | 直接调用 | 通过 SKILL.md 描述，Agent 自动选择 |

**SKILL.md 规范**：每个技能是一个目录，至少包含一个 `SKILL.md`。YAML frontmatter 中 `name` 和 `description` 是必填字段。`description` 决定 Agent 能否正确识别技能的适用场景。可选子目录：`scripts/`、`references/`、`assets/`。

**渐进披露机制**：Agent 启动时只加载技能名称和描述（约 100 token），任务匹配时才加载完整的 SKILL.md 正文，需要资源时才读取 `references/` 或执行 `scripts/`。

### 3.2 CodeGraph 是什么

CodeGraph 是一个本地代码知识图谱工具，基于 tree-sitter 解析 AST，提取函数、类、方法节点和调用、导入、继承边，存储在 SQLite 中，通过 MCP 协议暴露给 Agent。

**核心价值**：Agent 不再逐个读文件，而是先查图，图告诉你该读哪些文件。上下文消耗从 O(文件数) 降到 O(相关符号数)。

**性能对比**（官方 benchmark）：

| 指标 | 有 CodeGraph | 无 CodeGraph |
|------|-------------|-------------|
| 工具调用 | 基线 | 多 89% |
| Token 消耗 | 基线 | 多 69% |
| 文件读取 | 0 次 | 多次 |

**支持语言**：19+，包括 Python、Java、C/C++、Go、Rust 等。

**MCP 工具**：`codegraph_search`、`codegraph_callers`、`codegraph_callees`、`codegraph_impact`、`codegraph_node`、`codegraph_files` 等。

### 3.3 业务规则抽取的关键认知

- 超过 70% 的企业业务规则存在于应用代码中，但只有约 20% 的代码包含相关业务规则。
- 不能把整个代码库丢给模型找业务逻辑，必须先用静态分析筛选候选片段。
- 业务规则抽取需要业务上下文作为输入（专家访谈、需求文档），做交叉验证。
- 输出必须附带代码位置引用，否则业务人员无法核实。

---

## 4. 架构设计

### 4.1 目录结构

```
code-analyzer/
├── skills/
│   ├── project-structure/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── analyze.py
│   ├── file-summary/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── summarize.py
│   ├── dependency-analysis/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── analyze_deps.py
│   └── business-rule-extraction/
│       ├── SKILL.md
│       └── scripts/
│           └── extract_rules.py
├── agent/
│   ├── orchestrator.py      # 技能调度器
│   ├── llm_client.py        # 统一 LLM 调用
│   └── config.py            # 配置管理
├── server/
│   └── app.py               # FastAPI 后端（第四周）
├── static/
│   ├── index.html           # 前端页面（第四周）
│   ├── app.js
│   └── style.css
├── tests/
│   └── ...
├── .env.example
├── requirements.txt
├── README.md
└── PROJECT_PLAN.md          # 本文件
```

### 4.2 核心模块职责

| 模块 | 职责 |
|------|------|
| `agent/orchestrator.py` | 读取所有 Skill 的元数据，根据用户请求选择技能，执行并汇总结果 |
| `agent/llm_client.py` | 统一管理 LLM API 调用、重试、token 计数、缓存 |
| `skills/*/SKILL.md` | 定义技能名称、描述、输入输出格式、执行流程 |
| `skills/*/scripts/*.py` | 技能的具体实现，通过标准输入输出通信（JSON 进，JSON 出） |
| `server/app.py` | 提供 HTTP 接口，调用 orchestrator，返回 JSON |
| `static/` | 前端页面，展示分析结果 |

### 4.3 技能通信协议

所有技能脚本遵循统一约定：

- **输入**：从标准输入读取 JSON，包含 `input` 和 `context` 两个字段
- **输出**：向标准输出写入 JSON，包含 `status`、`data`、`error` 三个字段
- **错误处理**：失败时 `status` 为 `"error"`，`error` 字段包含错误信息

示例：

```json
// 输入
{
  "input": {
    "project_path": "/path/to/project"
  },
  "context": {
    "llm_config": {...}
  }
}

// 输出
{
  "status": "success",
  "data": {
    "modules": [...],
    "dependencies": [...]
  },
  "error": null
}
```

---

## 5. 技能详细设计

### 5.1 Skill 1：项目结构分析

**名称**：`project-structure`

**描述**：分析代码项目的目录结构、模块划分、构建配置，输出模块列表和模块间依赖关系。Use when analyzing project structure, module layout, or build configuration.

**输入**：
```json
{
  "project_path": "string"
}
```

**输出**：
```json
{
  "modules": [
    {
      "name": "string",
      "path": "string",
      "files": ["string"],
      "type": "source|test|config|docs"
    }
  ],
  "build_system": "maven|gradle|npm|pip|other",
  "dependencies": [
    {
      "from": "module_name",
      "to": "module_name",
      "type": "import|compile|runtime"
    }
  ]
}
```

**执行流程**：
1. 扫描项目根目录，识别构建文件（pom.xml、build.gradle、package.json、requirements.txt 等）
2. 根据构建文件和目录结构识别模块边界
3. 对每个模块，列出其包含的文件
4. 提取模块间依赖关系（通过解析构建文件或扫描 import）
5. 输出 JSON

**依赖**：无（纯静态分析，不需要 LLM）

**验收标准**：
- 能正确识别 Maven 多模块项目、Python 包结构
- 模块依赖关系准确率 > 90%
- 处理 1000 个文件的项目时，执行时间 < 10 秒

---

### 5.2 Skill 2：单文件语义摘要

**名称**：`file-summary`

**描述**：对单个代码文件生成语义摘要，包含文件职责、定义的符号列表、外部依赖列表。Use when summarizing a single code file, extracting symbols, or understanding file responsibilities.

**输入**：
```json
{
  "file_path": "string",
  "language": "string (optional)"
}
```

**输出**：
```json
{
  "file_path": "string",
  "language": "string",
  "responsibility": "string",
  "symbols": [
    {
      "name": "string",
      "type": "function|class|method|variable",
      "line_start": "number",
      "line_end": "number",
      "signature": "string (optional)"
    }
  ],
  "imports": ["string"],
  "external_dependencies": ["string"]
}
```

**执行流程**：
1. 读取文件内容
2. 识别语言（根据扩展名）
3. 提取符号定义（用 AST 或正则，Python 用 `ast` 模块）
4. 提取 import 语句
5. 调用 LLM 生成文件职责描述（只发送符号列表和 import，不发送全文）
6. 输出 JSON

**依赖**：LLM（仅用于生成职责描述）

**验收标准**：
- 符号提取准确率 > 95%
- 职责描述准确、简洁（不超过 100 字）
- 单文件处理时间 < 3 秒

---

### 5.3 Skill 3：依赖与调用链分析

**名称**：`dependency-analysis`

**描述**：分析指定符号（函数/类/模块）的调用者和被调用者，构建调用链路径。Use when analyzing call chains, dependencies, or impact of a symbol.

**输入**：
```json
{
  "project_path": "string",
  "target_symbol": "string",
  "direction": "callers|callees|both"
}
```

**输出**：
```json
{
  "target": "string",
  "callers": [
    {
      "symbol": "string",
      "file": "string",
      "line": "number"
    }
  ],
  "callees": [
    {
      "symbol": "string",
      "file": "string",
      "line": "number"
    }
  ],
  "call_chain": [
    {
      "path": ["symbol1", "symbol2", "symbol3"],
      "depth": "number"
    }
  ]
}
```

**执行流程（接入 CodeGraph 前）** ：
1. 解析项目所有文件的 AST
2. 提取函数定义和调用关系
3. 构建全局符号表
4. 根据目标符号，做图遍历
5. 输出 JSON

**执行流程（接入 CodeGraph 后）** ：
1. 调用 `codegraph_callers` 获取调用者
2. 调用 `codegraph_callees` 获取被调用者
3. 调用 `codegraph_impact` 获取影响范围
4. 输出 JSON

**依赖**：AST 解析库（tree-sitter）或 CodeGraph

**验收标准**：
- 能正确处理跨文件调用
- 调用链深度至少支持 5 层
- 处理 1000 个文件的项目时，查询时间 < 5 秒

---

### 5.4 Skill 4：业务规则抽取

**名称**：`business-rule-extraction`

**描述**：从代码中抽取业务规则，输出面向业务人员的自然语言描述，附带代码位置引用。Use when extracting business rules, domain logic, or business workflows from code.

**输入**：
```json
{
  "project_path": "string",
  "business_context": "string (optional)",
  "focus_modules": ["string"] (optional)
}
```

**输出**：
```json
{
  "rules": [
    {
      "id": "string",
      "description": "string",
      "category": "validation|calculation|workflow|constraint|other",
      "code_references": [
        {
          "file": "string",
          "line_start": "number",
          "line_end": "number",
          "snippet": "string"
        }
      ],
      "confidence": "high|medium|low"
    }
  ]
}
```

**执行流程**：
1. 用静态分析筛选候选代码片段：
   - 条件分支（if/switch）
   - 校验逻辑（参数检查、边界检查）
   - 状态转换（状态机、枚举切换）
   - 计算逻辑（金额、税率、折扣）
   - 异常抛出
2. 只把候选片段（不是整个代码库）送给 LLM
3. LLM 输出业务规则的自然语言描述 + 代码位置引用
4. 如果有业务上下文输入，做交叉验证
5. 输出 JSON

**依赖**：LLM + 静态分析

**验收标准**：
- 能识别出至少 10 条有意义的业务规则
- 每条规则必须有代码位置引用
- 误报率 < 30%
- 处理 1000 个文件的项目时，执行时间 < 5 分钟

---

## 6. 周计划详细展开

### 第一周：Skill 化改造

**目标**：把现有的“一个脚本跑到底”改造成有明确技能边界的 Agent。

#### Day 1：理解 Skill 规范

- 阅读 Anthropic Agent Skills 规范
- 阅读 2-3 个实际的开源 Skill 项目（如 ai-skills、catalogify）
- 理解 SKILL.md 的 YAML frontmatter 结构
- 理解渐进披露机制

**产出**：一份笔记，记录 Skill 的目录结构和 SKILL.md 模板

#### Day 2：设计技能清单和通信协议

- 确定第一周要做的两个技能：`project-structure` 和 `file-summary`
- 定义技能通信协议（JSON 输入输出格式）
- 定义编排器的职责和接口

**产出**：技能设计文档（可以写在 PROJECT_PLAN.md 的附录里）

#### Day 3-4：实现技能框架和两个基础技能

- 搭建项目骨架（目录结构如 4.1 节）
- 实现 `agent/llm_client.py`
- 实现 `agent/orchestrator.py`
- 实现 `skills/project-structure/`
- 实现 `skills/file-summary/`

**产出**：可运行的代码

#### Day 5：跑通第一个闭环

- 用 `Py_test` 或 `c_test_project` 验证
- 测试编排器能否根据自然语言请求选择正确技能
- 修复 bug

**第一周验收标准**：
- 两个 Skill 都能独立运行，输入输出格式正确
- 编排器能根据自然语言请求选择正确的技能
- 输出是 JSON，不是 Markdown

---

### 第二周：Skill 深化 + 业务逻辑分析

**目标**：增加两个新技能，其中一个聚焦业务逻辑分析。

#### Day 1-2：实现 `dependency-analysis` 技能

- 用 Python `ast` 模块解析 Python 文件
- 用 tree-sitter 解析其他语言（先支持 Python 和 Java）
- 构建全局符号表
- 实现调用链查询

**产出**：`skills/dependency-analysis/`

#### Day 3-4：实现 `business-rule-extraction` 技能

- 实现候选片段筛选逻辑
- 设计 LLM 提示词，要求输出结构化 JSON
- 实现交叉验证逻辑（如果有业务上下文）
- 测试并调整

**产出**：`skills/business-rule-extraction/`

#### Day 5：整合与测试

- 把四个技能串起来
- 用一个真实的遗留项目测试
- 观察业务规则抽取的准确率
- 修复 bug

**第二周验收标准**：
- 四个技能都能独立运行
- 业务规则抽取能识别出至少 5 条有意义的规则
- 所有输出都是结构化 JSON

---

### 第三周：接入 CodeGraph

**目标**：用 CodeGraph 替代当前的“逐个文件扫描”模式。

#### Day 1：安装和配置 CodeGraph

```bash
# 方式一：npm 全局安装
npm i -g @colbymchenry/codegraph
codegraph install

# 方式二：参考官方 README 的一键安装命令
```

接入 MCP 客户端：

```bash
codegraph install --target=claude --yes
```

在项目目录初始化索引：

```bash
cd your-project
codegraph init -i
```

**产出**：可运行的 CodeGraph 环境

#### Day 2-3：把 CodeGraph 接入 `dependency-analysis` 技能

- 修改技能实现，从“自己解析 AST”改为“查询 CodeGraph”
- 调用 `codegraph_callers`、`codegraph_callees`、`codegraph_impact`
- 保留原有的 AST 解析作为 fallback

**产出**：改造后的 `dependency-analysis`

#### Day 4-5：用大项目验证

- 找一个 1000+ 文件的开源项目
- 用接入 CodeGraph 后的 Agent 跑一遍
- 对比接入前后的 token 消耗、执行时间、分析覆盖度

**第三周验收标准**：
- CodeGraph 成功集成到至少两个技能中
- 能处理 1000+ 文件的项目而不爆上下文
- 技能查询 CodeGraph 的响应在秒级

---

### 第四周（可选）：前端展示 + 开源准备

**目标**：做一个简单的 HTML 页面展示分析结果，同时准备 GitHub 开源。

#### Day 1-3：做一个最小前端

- 用 FastAPI 包一层后端
- 实现 `/analyze` 接口，接收项目路径，返回 JSON
- 实现 `/report` 接口，返回 HTML 报告
- 前端页面：输入框 + 按钮 + 结果展示区（分标签页）

**产出**：`server/` 和 `static/`

#### Day 4-5：开源准备

- 写 README：项目定位、安装方式、使用示例、架构图
- 写 CONTRIBUTING.md：如何添加新 Skill
- 录制一个 2 分钟的演示视频/GIF
- 在 GitHub 上创建仓库，推代码

**第四周验收标准**：
- 前端能正常展示分析结果
- README 清晰易懂
- 仓库可以公开访问

---

## 7. 避坑指南

### 7.1 不要第一周就接 CodeGraph

CodeGraph 是基础设施，应该在你有了明确的技能边界之后再接入。先想清楚“我需要图来回答什么问题”，再去查图。否则你会花大量时间在配置上，却不知道图该怎么用。

### 7.2 业务规则抽取不要追求全量覆盖

能识别出 10 条高质量规则，比识别出 100 条模糊规则有价值得多。每条规则必须有代码位置引用，否则业务人员无法核实。

### 7.3 SKILL.md 的 description 字段很关键

Agent 是根据这个字段来决定是否加载某个技能的。写的时候要把触发关键词包含进去，比如“Use when analyzing code structure, dependencies, or call chains”。

### 7.4 保持所有技能的输出格式一致

统一用 JSON，字段命名统一（比如都用 `module_path`、`symbol_name`、`references`）。这样后续做前端和写入本体时才不会乱。

### 7.5 不要过早引入复杂框架

当前阶段不需要 LangChain、LangGraph。手写编排器更容易调试，也更容易理解 Agent 的本质。等技能多到手工管理不过来时，再考虑引入框架。

### 7.6 控制成本

- 用 DeepSeek flash 或其他便宜模型
- 对简单任务用轻量模型，复杂推理才用强模型
- 缓存重复的分析结果
- 限制单次分析的文件数量（比如最多 50 个），超出部分提示用户分批分析

---

## 8. 当前待办清单

- [ ] 阅读 Anthropic Agent Skills 规范
- [ ] 阅读 2-3 个开源 Skill 项目
- [ ] 设计技能通信协议
- [ ] 搭建项目骨架
- [ ] 实现 `llm_client.py`
- [ ] 实现 `orchestrator.py`
- [ ] 实现 `project-structure` 技能
- [ ] 实现 `file-summary` 技能
- [ ] 用 `Py_test` 跑通第一个闭环

---

## 9. 附录：参考资源

- Anthropic Agent Skills 规范：https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills
- CodeGraph 官方仓库：https://github.com/colbymchenry/codegraph
- tree-sitter 官方文档：https://tree-sitter.github.io/tree-sitter/
- MCP 协议规范：https://modelcontextprotocol.io/
- 论文《Harness Engineering: Anatomy, Architecture, and Evolution of Coding Agents》
- 论文《LLM Driven Business Rule Extraction from Enterprise Applications》
- 论文《Agentic Multi-Modal LLMs for Software Comprehension》

---

*本文档将随项目推进持续更新。*