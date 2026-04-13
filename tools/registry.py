"""Tool Registry - Central registry for all tools"""

from typing import Any, Dict, List, Optional
from .base import Tool


def _validate_input(schema: dict, data: dict) -> list[str]:
    """Lightweight JSON schema validation for tool inputs.

    Checks required fields and basic type constraints. Returns a list of
    error strings (empty = valid).
    """
    errors: list[str] = []
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    for field in required:
        if field not in data:
            errors.append(f"Missing required parameter: '{field}'")

    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for key, value in data.items():
        if key not in props:
            continue
        expected = props[key].get("type")
        if expected and expected in type_map:
            py_types = type_map[expected]
            if not isinstance(value, py_types):
                errors.append(
                    f"Parameter '{key}': expected {expected}, got {type(value).__name__}"
                )

    return errors


class ToolRegistry:
    """
    Central registry for all tools

    Manages tool registration, lookup, and execution.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool exists"""
        return name in self._tools

    def get_schemas(self) -> List[dict]:
        """Get schemas for all registered tools"""
        return [tool.to_schema() for tool in self._tools.values()]

    def is_io_intensive(self, name: str) -> bool:
        """Check if a tool is IO-intensive"""
        tool = self._tools.get(name)
        return tool.is_io_intensive if tool else False

    def is_dangerous(self, name: str) -> bool:
        """Check if a tool is dangerous"""
        tool = self._tools.get(name)
        return tool.is_dangerous if tool else False

    async def execute(self, name: str, input: dict) -> Any:
        """Execute a tool by name with given input.

        Validates ``input`` against the tool's JSON schema before calling. If
        validation fails, returns a descriptive error string (instead of
        crashing) so the LLM can self-correct.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found. Available tools: {list(self._tools.keys())}")

        errors = _validate_input(tool.input_schema, input or {})
        if errors:
            return f"Input validation error: {'; '.join(errors)}"

        return await tool.execute(**input)

    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())

    def list_tools_info(self) -> List[dict]:
        """Get info about all tools"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "is_io_intensive": tool.is_io_intensive,
                "is_dangerous": tool.is_dangerous,
            }
            for tool in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())