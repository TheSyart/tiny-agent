"""
Skill Creator — lets the agent autonomously write and hot-load new skills.

The agent can call create_skill() to generate a new Python skill file,
which is written to skills/custom/ and immediately hot-loaded via the
WebUI API (if running), or saved for next restart.
"""
import re
import ast
import asyncio
from pathlib import Path

from skills.base import Skill, SkillInfo
from tools.base import tool


class SkillCreatorSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="skill_creator",
            description="让 Agent 自主编写新技能并热加载，扩展自身能力",
            version="1.1.0",
            author="builtin",
            tags=["builtin", "meta", "self-improvement"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [create_skill, create_knowledge_skill, get_skill_template]


@tool
async def create_skill(name: str, description: str, code: str) -> str:
    """Write a new skill file to skills/custom/{name}/skill.py and hot-load it.

    The code must follow the tiny-agent skill format:
    - Import Skill, SkillInfo from skills.base
    - Import @tool from tools.base
    - Define a class inheriting Skill with info property and get_tools()
    - Define @tool async functions outside the class

    Args:
        name: Skill identifier, e.g. 'weather_lookup' (letters/digits/underscores only)
        description: One-line description of what the skill does
        code: Complete Python code for the skill file
    """
    # Validate name
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
        return "错误：name 必须以字母开头，只含字母/数字/下划线"

    # Validate code is parseable Python
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"错误：代码语法有误 — {e}"

    # Locate skills/custom directory (relative to this file's project root)
    project_root = Path(__file__).parent.parent.parent.parent
    skill_dir = project_root / "skills" / "custom" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "skill.py"
    skill_file.write_text(code, encoding="utf-8")

    # Attempt hot-load via WebUI API (best-effort)
    hot_loaded = False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:8000/api/skills",
                json={"name": name, "code": code},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hot_loaded = data.get("loaded", False)
    except Exception:
        pass

    if hot_loaded:
        return (
            f"✅ 技能 '{name}' 已创建并热加载成功！\n"
            f"文件：{skill_file}\n"
            f"现在可以直接调用该技能的工具，无需重启。"
        )
    else:
        return (
            f"📁 技能 '{name}' 代码已写入：{skill_file}\n"
            f"热加载未成功（WebUI 可能未运行）。\n"
            f"重启服务后技能将自动加载，或在 Web UI 技能页手动热加载。"
        )


@tool
async def create_knowledge_skill(name: str, description: str, content: str) -> str:
    """Create a SKILL.md knowledge file that teaches the agent a workflow or procedure.

    Use this to save reusable workflows, CLI tool guides, API usage patterns, or
    any step-by-step procedure the agent should recall on demand.

    Args:
        name: Skill identifier (letters/digits/underscores, e.g. 'git_workflow')
        description: One-line description shown in the skill catalog
        content: Full Markdown content (workflow steps, examples, notes, etc.)
    """
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
        return "错误：name 必须以字母开头，只含字母/数字/下划线"

    project_root = Path(__file__).parent.parent.parent.parent
    skill_dir = project_root / "skills" / "custom" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"

    full_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{content.strip()}\n"
    skill_file.write_text(full_md, encoding="utf-8")

    # Attempt hot-reload via WebUI API
    hot_loaded = False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:8000/api/skills",
                json={"name": name, "description": description, "content": content, "type": "knowledge"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hot_loaded = data.get("loaded", False)
    except Exception:
        pass

    if hot_loaded:
        return (
            f"✅ 知识技能 '{name}' 已创建并热加载！\n"
            f"文件：{skill_file}\n"
            f"现在可以用 load_skill('{name}') 调用完整指南。"
        )
    return (
        f"📁 知识技能 '{name}' 已写入：{skill_file}\n"
        f"热加载未成功（WebUI 可能未运行）。重启后可用 load_skill('{name}') 调用。"
    )


@tool
async def get_skill_template(skill_type: str = "basic") -> str:
    """Get a skill code template to use as a starting point when creating new skills.

    Args:
        skill_type: Template type — 'basic', 'http_api', 'cli_wrapper', 'data_transform'
    """
    templates = {
        "basic": '''\
from skills.base import Skill, SkillInfo
from tools.base import tool


class MySkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="my_skill",
            description="描述这个技能的功能",
            version="1.0.0",
            author="",
            tags=["custom"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [my_tool]


@tool
async def my_tool(param: str) -> str:
    """工具功能描述。
    Args:
        param: 参数说明
    """
    # 在这里实现工具逻辑
    return f"结果: {param}"
''',

        "http_api": '''\
import aiohttp
from skills.base import Skill, SkillInfo
from tools.base import tool


class HttpApiSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="http_api_skill",
            description="调用外部 HTTP API 的技能模板",
            version="1.0.0",
            author="",
            tags=["custom", "api"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [call_api]


@tool
async def call_api(url: str, params: str = "") -> str:
    """Call an external HTTP API and return the response.
    Args:
        url: Full URL to call
        params: Query parameters as 'key=value&key2=value2'
    """
    import urllib.parse
    query = dict(urllib.parse.parse_qsl(params)) if params else {}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=query, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            return f"Status: {resp.status}\\n{text[:2000]}"
''',

        "cli_wrapper": '''\
import asyncio
from skills.base import Skill, SkillInfo
from tools.base import tool


class CliWrapperSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="cli_wrapper_skill",
            description="封装命令行工具的技能模板",
            version="1.0.0",
            author="",
            tags=["custom", "cli"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [run_cli_tool]


@tool
async def run_cli_tool(args: str) -> str:
    """Run a CLI tool and return its output.
    Args:
        args: Command arguments (will be appended to the base command)
    """
    # 替换 YOUR_CLI_TOOL 为实际命令
    cmd = f"YOUR_CLI_TOOL {args}"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    output = stdout.decode() if stdout else ""
    error  = stderr.decode() if stderr else ""
    if proc.returncode != 0:
        return f"错误 (code {proc.returncode}):\\n{error or output}"
    return output or "(无输出)"
''',

        "data_transform": '''\
import json
from skills.base import Skill, SkillInfo
from tools.base import tool


class DataTransformSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="data_transform_skill",
            description="数据格式转换技能模板（JSON/CSV/文本处理）",
            version="1.0.0",
            author="",
            tags=["custom", "data"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [transform_json, extract_fields]


@tool
async def transform_json(json_str: str, jq_path: str) -> str:
    """Extract a value from JSON using a simple dot-notation path.
    Args:
        json_str: JSON string to parse
        jq_path: Dot-notation path, e.g. 'data.items.0.name'
    """
    try:
        obj = json.loads(json_str)
        for key in jq_path.split("."):
            if isinstance(obj, list):
                obj = obj[int(key)]
            else:
                obj = obj[key]
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"解析失败: {e}"


@tool
async def extract_fields(json_str: str, fields: str) -> str:
    """Extract specific fields from a JSON object or list of objects.
    Args:
        json_str: JSON string
        fields: Comma-separated field names, e.g. 'name,age,email'
    """
    try:
        obj = json.loads(json_str)
        keys = [f.strip() for f in fields.split(",")]
        if isinstance(obj, list):
            rows = [{k: item.get(k) for k in keys} for item in obj]
            return json.dumps(rows, ensure_ascii=False, indent=2)
        return json.dumps({k: obj.get(k) for k in keys}, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"提取失败: {e}"
''',
    }

    t = templates.get(skill_type.lower())
    if t:
        return f"=== {skill_type} 模板 ===\n\n```python\n{t}\n```"
    return f"未知模板类型。可用：{', '.join(templates.keys())}"
