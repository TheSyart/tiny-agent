"""Prompts module for Tiny-Agent.

This module provides prompt templates for the agent.
"""

import os
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


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