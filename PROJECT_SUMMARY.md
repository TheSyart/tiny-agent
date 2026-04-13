# Tiny-Agent 项目概览

> 一个生产级 AI Agent 框架，支持工具扩展、记忆管理、安全控制和 Web UI。

---

## 架构总览

```
tiny-agent/
├── main.py               # 入口：创建 Agent、注册工具/技能、启动 CLI 或 Web UI
├── config.yaml           # 全局配置（LLM / Memory / Safety / Skills / MCP）
├── prompts/tiny.md       # Agent 人格设定与工具调用规则（支持热更新）
│
├── agent/                # Agent 核心
│   ├── loop.py           # AgentLoop：主循环、流式输出、step_start 事件
│   ├── llm_client.py     # LLM 客户端（兼容 OpenAI 协议）
│   ├── session.py        # 会话管理
│   ├── hooks.py          # Hook 注册表（LOOP_START / TOOL_CALL 等事件）
│   └── logger.py         # 结构化日志
│
├── tools/                # 工具层
│   ├── builtin.py        # 内置工具注册（file_read/write, shell_exec, web_search）
│   ├── web.py            # web_search（duckduckgo-search 库）
│   ├── file.py           # 文件读写工具
│   ├── shell.py          # shell_exec 工具
│   ├── memory_tool.py    # save_important_memory / memory_recall
│   ├── system_prompt_tool.py  # update_system_prompt（热更新 tiny.md）
│   └── knowledge_skill_tool.py  # load_skill / list_knowledge_skills
│
├── memory/               # 记忆系统
│   ├── manager.py        # MemoryManager：短期 + 向量检索 + 归档
│   └── compressor.py     # Token 比例触发压缩（70% 上下文时自动压缩）
│
├── safety/               # 安全管理
│   └── manager.py        # SafetyManager：sandbox / confirm / trust 三模式
│
├── skills/               # 技能系统（双层架构）
│   ├── base.py           # Skill 基类 + SkillInfo
│   ├── loader.py         # SkillLoader：自动发现并加载 skill.py
│   ├── builtin/          # 内置技能
│   │   ├── calculator/   # 数学计算 + 单位换算
│   │   ├── datetime_info/ # 时间日期查询 + 时区转换
│   │   ├── skill_creator/ # 自主创建技能（Python + SKILL.md 两种类型）
│   │   ├── web_research/SKILL.md   # 网络调研工作流（知识技能）
│   │   ├── code_review/SKILL.md    # 代码审查清单（知识技能）
│   │   └── git_workflow/SKILL.md   # Git 操作速查（知识技能）
│   └── custom/           # 用户创建的技能（热加载，无需重启）
│       └── nano_banana_2/SKILL.md  # Gemini 图片生成（知识技能）
│
├── mcp/                  # MCP 服务器连接
│   └── connector.py      # MCPConnector：add/remove/reload server
│
├── webui/                # Web UI（FastAPI + 原生 JS）
│   ├── app.py            # REST API + WebSocket 端点
│   └── static/
│       ├── index.html    # 单页应用（7 个功能页面）
│       ├── js/
│       │   ├── app.js        # 聊天页面逻辑
│       │   ├── nav.js        # 导航切换 + 页面进入回调
│       │   ├── mcp-skills.js # MCP 管理 + 技能页面 + 技能创建器
│       │   ├── memory.js     # 记忆管理页面
│       │   └── config.js     # 模型/工具/提示词配置页面
│       └── css/
│           ├── base.css      # 颜色变量、全局样式（Soft Dark 主题）
│           ├── layout.css    # 导航栏 + 页面布局
│           ├── chat.css      # 聊天气泡、工具卡片、步骤分隔线
│           └── panels.css    # 配置页面卡片、表单、技能编辑器
│
└── data/                 # 运行时数据
    ├── memory/           # 短期记忆（history.json）+ 重要记忆（memory.md）
    └── metrics/          # Token 使用统计（usage.jsonl + stats.py）
```

---

## 技能双层架构（核心设计）

受 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 启发，技能系统分两层：

### Layer 1 — Python 工具技能（`skill.py`）
- **作用**：为 Agent 添加可调用的函数工具
- **加载**：`SkillLoader` 自动发现，工具注册到 `agent.tools`
- **示例**：`calculate(expr)`, `get_current_datetime()`, `unit_convert()`
- **创建**：`create_skill(name, description, code)` 工具或 Web UI

### Layer 2 — 知识技能（`SKILL.md`）
- **作用**：向 Agent 注入领域知识、操作指南、工作流程
- **加载**：`KnowledgeSkillRegistry` 扫描，仅描述注入系统提示（轻量）；完整内容按需加载（`load_skill`）
- **示例**：web_research, code_review, git_workflow, nano_banana_2
- **创建**：`create_knowledge_skill(name, description, content)` 工具或 Web UI

> **设计原则**：系统提示只包含技能名称和一行描述（节省 token），当 Agent 需要使用某技能时，调用 `load_skill("name")` 获取完整指南。

---

## Web UI 页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 聊天 | `page-chat` | 主聊天界面，流式输出，步骤分隔线 |
| 提示词 | `page-prompt` | 编辑 tiny.md，保存后热生效 |
| 模型 | `page-model` | 调整 model/temperature/max_tokens |
| 工具 | `page-tools` | 查看已注册工具列表 |
| MCP | `page-mcp` | 管理 MCP 服务器（添加/删除/重连） |
| 技能 | `page-skills` | 查看已加载技能，创建新技能（Python/SKILL.md） |
| 记忆 | `page-memory` | 短期记忆、历史归档、重要记忆查看 |
| 统计 | `page-stats` | Token 消耗统计、费用估算、14 天趋势 |

---

## REST API 端点

### 聊天
- `WS /ws/chat` — 流式对话（step_start / text / tool_call / tool_result / done）
- `GET /api/memory/chat-history` — 加载历史消息（页面刷新时恢复对话）

### 配置
- `GET/PATCH /api/config` — 模型参数
- `GET/PATCH /api/config/prompt` — 系统提示词

### 工具 & 技能
- `GET /api/tools` — 工具列表
- `GET /api/skills` — 技能列表（Python + 知识技能）
- `POST /api/skills` — 创建技能（`type: "python"` 或 `type: "knowledge"`）

### MCP
- `GET /api/mcp/servers` — 服务器列表（含连接状态）
- `POST /api/mcp/servers` — 添加服务器
- `DELETE /api/mcp/servers/{name}` — 删除服务器
- `POST /api/mcp/servers/{name}/reload` — 重连服务器

### 记忆
- `GET /api/memory/short-term` — 短期消息
- `GET /api/memory/important` — memory.md 内容
- `POST /api/memory/compress` — 手动触发压缩

### 统计
- `GET /api/metrics/usage?days=14` — Token 使用统计

---

## 内置工具（已注册）

| 工具 | 描述 |
|------|------|
| `file_read` | 读取文件内容 |
| `file_write` | 写入文件 |
| `file_edit` | 编辑文件（查找替换） |
| `grep` | 文件内容正则搜索（优先 ripgrep） |
| `glob_files` | 文件名 glob 模式匹配 |
| `shell_exec` | 执行 Shell 命令 |
| `web_search` | DuckDuckGo 网络搜索 |
| `web_fetch` | 抓取网页正文 |
| `save_important_memory` | 保存重要记忆到 memory.md |
| `memory_recall` | 向量检索历史记忆 |
| `update_system_prompt` | 热更新 Agent 人格设定 |
| `load_skill` | 按需加载知识技能全文 |
| `list_knowledge_skills` | 列出所有知识技能 |
| `calculate` | 安全数学表达式计算 |
| `unit_convert` | 单位换算 |
| `get_current_datetime` | 获取当前时间（支持时区） |
| `convert_timezone` | 时区转换 |
| `create_skill` | 创建 Python 工具技能 |
| `create_knowledge_skill` | 创建 SKILL.md 知识技能 |
| `get_skill_template` | 获取技能代码模板 |

---

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
export ANTHROPIC_API_KEY=sk-...
# 或在 config.yaml 中设置 llm.api_key

# 启动 Web UI（默认）
python main.py

# 启动 CLI 模式
python main.py --cli

# 跳过安全确认（开发调试）
python main.py --trust
```

Web UI 访问：http://localhost:8000

---

## 配置文件（config.yaml 关键项）

```yaml
llm:
  model: claude-sonnet-4-6      # 或任何 OpenAI 兼容模型
  base_url: https://api.anthropic.com/v1
  max_tokens: 8192

memory:
  type: simple                  # simple | vector
  max_messages: 100
  compression:
    enabled: true
    trigger_ratio: 0.70         # 上下文达 70% 时自动压缩

safety:
  mode: confirm                 # sandbox | confirm | trust

skills:
  auto_discover: true
  directories:
    - "./skills/builtin"
    - "./skills/custom"
```
