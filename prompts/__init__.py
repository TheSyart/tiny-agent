"""Prompts module for Tiny-Agent.

This module provides prompt templates and the SystemPromptBuilder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).parent

# Boundary marker — everything before this in the system prompt is
# stable across turns and eligible for Anthropic prompt caching.
DYNAMIC_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"


def load_prompt(name: str) -> str:
    """Load a prompt template by name.

    Args:
        name: Prompt filename (without .md extension)

    Returns:
        Prompt content as string
    """
    prompt_path = PROMPTS_DIR / f"{name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt not found: {name}")


def get_tiny_config() -> str:
    """Get the Tiny-Agent configuration prompt.

    Returns:
        Configuration prompt as string
    """
    return load_prompt("tiny")


class SystemPromptBuilder:
    """Build a structured system prompt with static/dynamic sections.

    Static sections are stable across turns and can benefit from Anthropic's
    prompt caching.  Dynamic sections change per request (datetime, memory,
    loaded skills, etc.).

    Usage::

        builder = SystemPromptBuilder()
        builder.add_static(get_tiny_config())
        builder.add_static(tool_usage_rules)
        builder.add_dynamic(skill_descriptions)
        builder.add_dynamic(memory_context)
        prompt = builder.build()
    """

    def __init__(self) -> None:
        self._static: list[str] = []
        self._dynamic: list[str] = []

    # ------------------------------------------------------------------
    # Fluent API
    # ------------------------------------------------------------------

    def add_static(self, section: str) -> "SystemPromptBuilder":
        """Add a section that is stable across turns."""
        if section:
            self._static.append(section)
        return self

    def add_dynamic(self, section: str) -> "SystemPromptBuilder":
        """Add a section that may change per request."""
        if section:
            self._dynamic.append(section)
        return self

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def build(self) -> str:
        """Return the full system prompt as a single string."""
        parts = self._static + self._dynamic
        return "\n\n".join(parts)

    def build_cached(self) -> list[dict]:
        """Return the system prompt as a list of cache-control blocks.

        The Anthropic API accepts ``system`` as a list of ``{"type": "text",
        "text": ..., "cache_control": ...}`` dicts.  Static sections are
        marked with ``cache_control: {"type": "ephemeral"}`` so the API can
        reuse them across turns without re-processing.
        """
        blocks: list[dict] = []

        # Static sections — cacheable
        if self._static:
            blocks.append({
                "type": "text",
                "text": "\n\n".join(self._static),
                "cache_control": {"type": "ephemeral"},
            })

        # Dynamic sections — not cached
        if self._dynamic:
            blocks.append({
                "type": "text",
                "text": "\n\n".join(self._dynamic),
            })

        return blocks

    @property
    def is_empty(self) -> bool:
        return not self._static and not self._dynamic