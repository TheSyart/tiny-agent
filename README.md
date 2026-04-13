# Tiny-Agent

> 一个轻量但完整的 AI Agent 框架：工具扩展、双层技能系统、记忆管理、安全控制、MCP 集成，配套原生 Web UI。

---

## 特性

- **Agent 核心循环**：流式输出、多轮工具调用、步骤事件、Hook 扩展点
- **工具系统**：参考 Claude Code 设计的精简工具集（Read/Write/Edit/Bash/Grep/Glob/WebSearch/WebFetch）
- **双层技能架构**：
  - Layer 1 — Python `skill.py` 注册可调用工具
  - Layer 2 — `SKILL.md` 知识技能，按需加载（节省上下文）
- **记忆管理**：短期历史 + 向量检索 + Token 比例触发的自动压缩；重要记忆独立存入 `memory.md`
- **安全管理**：`sandbox` / `confirm` / `trust` 三种模式，可配置危险工具清单
- **MCP 集成**：可在 Web UI 动态添加/删除/重连 MCP 服务器
- **Web UI**：FastAPI + 原生 JS，无前端构建工具；聊天、提示词、模型、工具、MCP、技能、记忆、统计 8 个页面
- **热更新**：人格设定、知识技能、MCP 服务器均可运行中修改

---

## 目录结构

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
│   ├── hooks.py          # Hook 注册表
│   └── logger.py         # 结构化日志
│
├── tools/                # 工具层（对标 Claude Code）
│   ├── builtin.py        # 内置工具注册入口
│   ├── file.py           # file_read / file_write / file_edit
│   ├── shell.py          # shell_exec
│   ├── search.py         # grep / glob_files（ripgrep + pathlib）
│   ├── web.py            # web_search / web_fetch
│   ├── memory_tool.py    # save_important_memory / memory_recall
│   ├── system_prompt_tool.py     # update_system_prompt
│   └── knowledge_skill_tool.py   # load_skill / list_knowledge_skills
│
├── memory/
│   ├── manager.py        # 短期 + 向量检索 + 重要记忆注入
│   └── compressor.py     # Token 比例触发压缩（默认 70% 上下文）
│
├── safety/
│   └── manager.py        # sandbox / confirm / trust 三模式
│
├── skills/               # 技能系统（双层架构）
│   ├── base.py           # Skill 基类 + SkillInfo
│   ├── loader.py         # SkillLoader：自动发现 skill.py
│   ├── builtin/
│   │   ├── calculator/          # 数学计算 + 单位换算
│   │   ├── datetime_info/       # 时间日期 + 时区
│   │   ├── skill_creator/       # 自主创建 Python / 知识技能
│   │   ├── web_research/SKILL.md
│   │   ├── code_review/SKILL.md
│   │   └── git_workflow/SKILL.md
│   └── custom/           # 用户创建的技能（热加载）
│       └── nano_banana_2/SKILL.md
│
├── mcp/
│   └── connector.py      # MCPConnector：add / remove / reload server
│
├── webui/
│   ├── app.py            # REST API + WebSocket 端点
│   └── static/
│       ├── index.html    # 单页应用
│       ├── js/
│       │   ├── app.js        # 聊天页逻辑（流式、思考气泡、步骤分隔）
│       │   ├── nav.js        # 导航切换
│       │   ├── mcp-skills.js # MCP + 技能页面
│       │   ├── memory.js     # 记忆管理页
│       │   └── config.js     # 模型/工具/提示词
│       └── css/
│           ├── base.css      # Soft Dark 主题变量
│           ├── layout.css    # 导航 + 页面布局
│           ├── chat.css      # 聊天气泡、工具卡片、步骤分隔
│           └── panels.css    # 配置页卡片、表单
│
└── data/
    ├── memory/           # history.json + memory.md
    └── metrics/          # usage.jsonl + stats.py
```

---

## 内置工具

对标 Claude Code 的核心工具集，精简后共 8 个：

| 工具 | 作用 | 对应 Claude Code |
|---|---|---|
| `file_read` | 读取文件内容 | Read |
| `file_write` | 写入/创建文件 | Write |
| `file_edit` | 查找替换式编辑 | Edit |
| `grep` | 正则内容搜索（优先 ripgrep） | Grep |
| `glob_files` | 文件名 glob 匹配（按 mtime 排序） | Glob |
| `shell_exec` | 执行 Shell 命令 | Bash |
| `web_search` | DuckDuckGo 网络搜索 | WebSearch |
| `web_fetch` | 抓取网页正文 | WebFetch |

外加扩展工具：

| 工具 | 作用 |
|---|---|
| `save_important_memory` | 写入 `data/memory/memory.md` |
| `memory_recall` | 向量检索历史记忆 |
| `update_system_prompt` | 热更新人格设定 |
| `load_skill` / `list_knowledge_skills` | 按需加载知识技能 |
| `create_skill` / `create_knowledge_skill` / `get_skill_template` | 自主创建技能 |
| `calculate` / `unit_convert` | 数学计算、单位换算 |
| `get_current_datetime` / `convert_timezone` | 时间、时区 |

---

## 技能双层架构

> 受 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 启发。

### Layer 1 — Python 工具技能（`skill.py`）

- 为 Agent 添加可调用的函数工具
- `SkillLoader` 自动扫描 → 工具注册到 `agent.tools`
- 示例：`calculate`, `get_current_datetime`, `unit_convert`

### Layer 2 — 知识技能（`SKILL.md`）

- 向 Agent 注入领域知识、操作指南、工作流
- 系统提示只注入 **名称 + 一行描述**（节省 token）
- Agent 需要时调用 `load_skill("name")` 获取完整内容
- 示例：`web_research`, `code_review`, `git_workflow`, `nano_banana_2`

---

## Web UI 页面

| 页面 | 功能 |
|---|---|
| 聊天 | 主交互界面；流式输出；思考气泡（可折叠）；多步加载指示；左右分栏布局 |
| 提示词 | 编辑 `tiny.md`，保存即热生效 |
| 模型 | 调整 model / temperature / max_tokens |
| 工具 | 查看已注册工具 |
| MCP | 添加/删除/重连 MCP 服务器 |
| 技能 | 查看技能；创建 Python 或 SKILL.md 技能 |
| 记忆 | 短期消息、重要记忆、手动压缩 |
| 统计 | Token 消耗、费用估算、14 天趋势 |

---

## REST API

### 聊天
- `WS /ws/chat` — 流式对话（事件：`step_start` / `thinking` / `text` / `tool_call` / `tool_result` / `done`）
- `GET /api/memory/chat-history` — 恢复历史对话（含 thinking 块）

### 配置
- `GET` / `PATCH` `/api/config` — 模型参数
- `GET` / `PATCH` `/api/config/prompt` — 系统提示词

### 工具 & 技能
- `GET /api/tools`
- `GET /api/skills`
- `POST /api/skills` — 创建技能（`type: "python"` 或 `"knowledge"`）

### MCP
- `GET /api/mcp/servers`
- `POST /api/mcp/servers`
- `DELETE /api/mcp/servers/{name}`
- `POST /api/mcp/servers/{name}/reload`

### 记忆 & 统计
- `GET /api/memory/short-term` / `/api/memory/important`
- `POST /api/memory/compress`
- `GET /api/metrics/usage?days=14`

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（二选一）
export ANTHROPIC_API_KEY=sk-...
# 或在 config.yaml 中设置 llm.api_key

# 3. 启动 Web UI（默认）
python main.py
# 访问 http://localhost:8000

# 其他启动模式
python main.py --cli      # 命令行模式
python main.py --trust    # 跳过安全确认（仅调试）
```

---

## 配置要点（`config.yaml`）

```yaml
llm:
  model: claude-sonnet-4-6
  base_url: https://api.anthropic.com/v1
  max_tokens: 8192

memory:
  type: simple                  # simple | vector
  max_messages: 100
  compression:
    enabled: true
    trigger_ratio: 0.70         # 上下文达 70% 触发压缩

safety:
  mode: confirm                 # sandbox | confirm | trust
  confirm:
    dangerous_tools:
      - shell_exec
      - file_write
      - file_edit

skills:
  auto_discover: true
  directories:
    - "./skills/builtin"
    - "./skills/custom"
```

---

## License

MIT
