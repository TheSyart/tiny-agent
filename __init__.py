"""Tiny-Agent - A lightweight AI agent framework"""

__version__ = "0.1.0"

from agent.loop import AgentLoop
from agent.types import (
    Message,
    ContentBlock,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)
from tools.base import Tool, tool
from tools.registry import ToolRegistry
from memory.manager import MemoryManager
from memory.short_term import ShortTermMemory
from skills.base import Skill, SkillInfo
from skills.loader import SkillLoader
from safety.manager import SafetyManager, SafetyMode, SafetyConfig

__all__ = [
    "AgentLoop",
    "Message",
    "ContentBlock",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "Tool",
    "tool",
    "ToolRegistry",
    "MemoryManager",
    "ShortTermMemory",
    "Skill",
    "SkillInfo",
    "SkillLoader",
    "SafetyManager",
    "SafetyMode",
    "SafetyConfig",
]