"""Tool system for Tiny-Agent"""

from .base import Tool, tool
from .registry import ToolRegistry

__all__ = ["Tool", "tool", "ToolRegistry"]