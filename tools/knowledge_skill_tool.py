"""
Knowledge Skill Tools — SKILL.md-based on-demand knowledge injection.

Inspired by learn-claude-code (shareAI-lab): skills are Markdown documents
describing *how to do something* (workflows, CLI usage, domain knowledge).
The agent uses `load_skill` to pull the full instructions only when needed,
keeping the base system prompt lean.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from tools.base import Tool


@dataclass
class SkillManifest:
    name: str
    description: str
    path: Path


@dataclass
class SkillDocument:
    manifest: SkillManifest
    body: str


class KnowledgeSkillRegistry:
    """Scans skills directories for SKILL.md files and serves them on demand."""

    def __init__(self, directories: List[str]):
        self._skills: Dict[str, SkillDocument] = {}
        for d in directories:
            self._scan(Path(d))

    def _scan(self, root: Path) -> None:
        if not root.exists():
            return
        for skill_file in root.rglob("SKILL.md"):
            try:
                doc = self._parse(skill_file)
                if doc:
                    self._skills[doc.manifest.name] = doc
            except Exception:
                pass

    def _parse(self, path: Path) -> Optional[SkillDocument]:
        raw = path.read_text(encoding="utf-8")
        # Extract YAML frontmatter between --- delimiters
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', raw, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            body = fm_match.group(2).strip()
        else:
            frontmatter = ""
            body = raw.strip()

        def _get(key: str, default: str = "") -> str:
            m = re.search(rf'^{key}\s*:\s*(.+)$', frontmatter, re.MULTILINE)
            return m.group(1).strip().strip('"\'') if m else default

        name = _get("name") or path.parent.name
        description = _get("description") or "(no description)"
        return SkillDocument(
            manifest=SkillManifest(name=name, description=description, path=path),
            body=body,
        )

    def list_skills(self) -> List[SkillManifest]:
        return list(s.manifest for s in self._skills.values())

    def get(self, name: str) -> Optional[SkillDocument]:
        return self._skills.get(name)

    def describe_available(self) -> str:
        """One-line description per skill — for injecting into system prompt."""
        if not self._skills:
            return ""
        lines = ["## 可用知识技能（调用 load_skill 获取完整指令）\n"]
        for doc in self._skills.values():
            lines.append(f"- **{doc.manifest.name}**: {doc.manifest.description}")
        return "\n".join(lines)

    def reload(self, directories: List[str]) -> None:
        self._skills.clear()
        for d in directories:
            self._scan(Path(d))


def make_knowledge_skill_tools(registry: KnowledgeSkillRegistry) -> List[Tool]:
    """Return [load_skill, list_skills] tools backed by the given registry."""

    async def _load_skill(name: str) -> str:
        doc = registry.get(name)
        if doc is None:
            available = [m.name for m in registry.list_skills()]
            return (
                f"未找到技能 '{name}'。"
                + (f" 可用：{', '.join(available)}" if available else " 暂无知识技能。")
            )
        return f"<skill name=\"{doc.manifest.name}\">\n{doc.body}\n</skill>"

    async def _list_skills(_: str = "") -> str:
        skills = registry.list_skills()
        if not skills:
            return "暂无知识技能。可在 skills/ 目录下创建 SKILL.md 文件添加。"
        lines = [f"共 {len(skills)} 个知识技能：\n"]
        for m in skills:
            lines.append(f"- **{m.name}**: {m.description}")
        return "\n".join(lines)

    load_tool = Tool(
        name="load_skill",
        description=(
            "Load the full instructions of a named knowledge skill. "
            "Call this when you need detailed guidance on a specific workflow, "
            "tool usage, or domain procedure (e.g. image generation, API integration). "
            "Use list_knowledge_skills first if unsure of the skill name."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name, e.g. 'nano_banana_2'"}
            },
            "required": ["name"],
        },
        handler=_load_skill,
    )

    list_tool = Tool(
        name="list_knowledge_skills",
        description="List all available knowledge skills with their descriptions.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional filter keyword"}
            },
        },
        handler=_list_skills,
    )

    return [load_tool, list_tool]
