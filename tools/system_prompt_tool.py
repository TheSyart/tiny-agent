"""Tool for dynamically updating the agent's system prompt (prompts/tiny.md).

When the user asks to modify the agent's personality or behavior settings,
the agent calls this tool to rewrite the file and hot-reload the live prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


def make_update_prompt_tool(prompt_path: str, agent_loop: Any) -> Tool:
    """Build an ``update_system_prompt`` tool bound to the agent loop.

    The tool writes *new_content* to *prompt_path* and immediately updates
    ``agent_loop.system_prompt`` so the change takes effect in the next
    LLM call without requiring a restart.
    """

    async def _handler(new_content: str) -> str:
        path = Path(prompt_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        agent_loop.config.system_prompt = new_content
        return "人格设定已更新，下一条消息起立即生效。"

    return Tool(
        name="update_system_prompt",
        description=(
            "Update the agent's character and system prompt (prompts/tiny.md). "
            "Use ONLY when the user explicitly asks to change the agent's personality, "
            "name, speaking style, or behavioral guidelines. "
            "new_content must be the COMPLETE new file content in Markdown — do not "
            "omit any existing sections unless the user explicitly asked to remove them."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "new_content": {
                    "type": "string",
                    "description": "Complete new Markdown content for the system prompt file.",
                },
            },
            "required": ["new_content"],
        },
        handler=_handler,
        is_io_intensive=False,
        is_dangerous=False,
    )
