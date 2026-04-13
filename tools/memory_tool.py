"""Memory tools exposed to the agent.

These tools let the LLM look back into the archived session store so it
can answer questions about prior conversations ("what did we discuss last
time about X?"). The memory manager is injected at registration time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Tool


def make_memory_recall_tool(memory_manager: Any) -> Tool:
    """Build a ``memory_recall`` tool bound to the given MemoryManager."""

    async def _handler(query: str, limit: int = 3) -> str:
        if memory_manager is None or getattr(memory_manager, "archive", None) is None:
            return "Archive is not enabled — no past sessions to recall."

        results = await memory_manager.recall_history(query=query, limit=limit)
        if not results:
            return f"No archived sessions matched: {query!r}"

        lines = [f"Found {len(results)} archived session(s) for: {query!r}", ""]
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.get('id', '?')}  ({r.get('created_at', '')})")
            tools = r.get("tool_calls") or []
            if tools:
                lines.append(f"    tools: {', '.join(tools)}")
            summary = (r.get("summary") or "").strip()
            if summary:
                truncated = summary if len(summary) <= 600 else summary[:600] + "…"
                lines.append(f"    summary: {truncated}")
            lines.append("")
        return "\n".join(lines).rstrip()

    return Tool(
        name="memory_recall",
        description=(
            "Search archived past conversations by keyword. Use this when the "
            "user references something from earlier sessions that is not in "
            "the current conversation context. Returns matching session IDs "
            "and summaries."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords or topic to search archived sessions for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of past sessions to return (default 3).",
                },
            },
            "required": ["query"],
        },
        handler=_handler,
        is_io_intensive=True,
        is_dangerous=False,
    )


def make_save_memory_tool(storage_path: str = "./data/memory") -> Tool:
    """Build a ``save_important_memory`` tool that appends to memory.md."""

    async def _handler(content: str) -> str:
        path = Path(storage_path) / "memory.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Initialize file with header if new
        if not path.exists():
            path.write_text("# 重要记忆\n", encoding="utf-8")
        entry = f"\n## {timestamp}\n\n{content.strip()}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
        return "已保存到 memory.md"

    return Tool(
        name="save_important_memory",
        description=(
            "Save an important fact, user preference, or project insight to "
            "persistent memory (memory.md). Use proactively when the user reveals "
            "preferences, project details, constraints, or anything worth "
            "remembering across sessions. Content should be concise and factual."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The important fact or preference to remember. Be concise.",
                },
            },
            "required": ["content"],
        },
        handler=_handler,
        is_io_intensive=False,
        is_dangerous=False,
    )
