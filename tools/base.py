"""Base tool implementation with decorator for auto schema inference"""

from functools import wraps
from typing import (
    Any,
    Callable,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
import inspect


class Tool:
    """
    Base class for tools

    A tool is a function that the LLM can call to perform actions.
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable,
        is_io_intensive: bool = False,
        is_dangerous: bool = False,
        is_concurrency_safe: Union[bool, Callable[[dict], bool], None] = None,
    ):
        """
        Initialize a tool

        Args:
            name: Tool name (used by LLM to call it)
            description: Tool description (helps LLM understand when to use it)
            input_schema: JSON Schema for input parameters
            handler: The actual function to execute
            is_io_intensive: Whether this tool does IO (kept for backward compat,
                maps to is_concurrency_safe)
            is_dangerous: Whether this tool can cause harm (needs confirmation)
            is_concurrency_safe: Whether this tool can run concurrently with
                other concurrency-safe tools.  Accepts a bool or a callable
                that receives the tool input dict and returns bool.  If None,
                falls back to ``is_io_intensive``.
        """
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler
        self.is_io_intensive = is_io_intensive
        self.is_dangerous = is_dangerous

        # Concurrency safety: prefer explicit flag, fall back to is_io_intensive
        if is_concurrency_safe is not None:
            self._concurrency_safe = is_concurrency_safe
        else:
            self._concurrency_safe = is_io_intensive

        # Pre-detect whether handler accepts a 'context' parameter so we can
        # inject ToolUseContext without breaking existing tools.
        try:
            sig = inspect.signature(handler)
            self._accepts_context = "context" in sig.parameters
        except (ValueError, TypeError):
            self._accepts_context = False

    def get_concurrency_safe(self, input: Optional[dict] = None) -> bool:
        """Return whether this tool can run concurrently given *input*."""
        if callable(self._concurrency_safe):
            return bool(self._concurrency_safe(input or {}))
        return bool(self._concurrency_safe)

    async def execute(self, context=None, **kwargs) -> Any:
        """Execute the tool with given arguments.

        If the handler function declares a ``context`` parameter, the
        :class:`~agent.context.ToolUseContext` is injected automatically.
        Existing handlers without that parameter are unaffected.
        """
        if self._accepts_context and context is not None:
            kwargs["context"] = context
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)
        return self.handler(**kwargs)

    def to_schema(self) -> dict:
        """Convert to LLM API schema format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_io_intensive: bool = False,
    is_dangerous: bool = False,
    is_concurrency_safe: Union[bool, Callable[[dict], bool], None] = None,
):
    """
    Decorator to create a tool from a function

    Automatically infers JSON Schema from type hints.

    Can be used as:
        @tool
        async def my_tool(...): ...

        @tool(is_concurrency_safe=True)
        async def my_tool(...): ...

    Args:
        name: Override tool name (defaults to function name)
        description: Override description (defaults to docstring)
        is_io_intensive: Mark as IO-intensive (deprecated, use is_concurrency_safe)
        is_dangerous: Mark as dangerous (requires user confirmation)
        is_concurrency_safe: Whether this tool can run concurrently with
            other concurrency-safe tools.  Falls back to is_io_intensive.
    """
    def decorator(func: Callable) -> Tool:
        # Get tool name
        tool_name = name or func.__name__

        # Get description from docstring
        tool_desc = description or _extract_description(func)

        # Infer schema from type hints
        input_schema = _infer_schema(func)

        return Tool(
            name=tool_name,
            description=tool_desc,
            input_schema=input_schema,
            handler=func,
            is_io_intensive=is_io_intensive,
            is_dangerous=is_dangerous,
            is_concurrency_safe=is_concurrency_safe,
        )

    # Handle @tool without parentheses (name is actually the function)
    if callable(name) and not isinstance(name, str):
        func = name
        name = None
        return decorator(func)

    return decorator


def _extract_description(func: Callable) -> str:
    """Extract description from function docstring"""
    doc = func.__doc__
    if not doc:
        return ""

    # Get the first paragraph (before Args:, Returns:, etc.)
    lines = doc.strip().split('\n')
    desc_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped in ('Args:', 'Returns:', 'Raises:', 'Example:', 'Examples:'):
            break
        if stripped:
            desc_lines.append(stripped)

    return ' '.join(desc_lines)


def _infer_schema(func: Callable) -> dict:
    """Infer JSON Schema from function signature"""
    hints = get_type_hints(func)
    sig = inspect.signature(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ('self', 'cls'):
            continue

        # Get parameter type
        param_type = hints.get(param_name, str)
        json_type, is_optional = _python_type_to_json_schema(param_type)

        # Get parameter description from docstring
        param_desc = _extract_param_description(func, param_name)

        properties[param_name] = {
            "type": json_type,
            "description": param_desc
        }

        # Required iff no default AND type is not Optional[...].
        if (
            param.default is inspect.Parameter.empty
            and not is_optional
        ):
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


def _python_type_to_json_schema(python_type) -> tuple[str, bool]:
    """Convert a Python type hint to ``(json_schema_type, is_optional)``.

    Handles ``Optional[T]`` / ``Union[T, None]`` / ``T | None`` by unwrapping
    to ``T`` and marking the parameter as optional. ``typing.get_origin`` +
    ``get_args`` are used instead of the legacy ``__origin__`` check (which
    never matched ``Optional``).
    """
    origin = get_origin(python_type)
    if origin is Union:
        args = [a for a in get_args(python_type) if a is not type(None)]
        if not args:
            return "string", True
        inner_type, _ = _python_type_to_json_schema(args[0])
        return inner_type, True

    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        List: "array",
    }

    # Parameterised generics like list[int] / dict[str, int]: use origin.
    if origin in type_map:
        return type_map[origin], False

    return type_map.get(python_type, "string"), False


def _extract_param_description(func: Callable, param_name: str) -> str:
    """Extract parameter description from docstring"""
    doc = func.__doc__
    if not doc:
        return ""

    lines = doc.split('\n')
    in_args = False
    current_param = None
    desc_parts = []

    for line in lines:
        stripped = line.strip()

        if stripped == 'Args:':
            in_args = True
            continue

        if in_args:
            if stripped in ('Returns:', 'Raises:', 'Example:', 'Examples:'):
                break

            # Check if this is a new parameter
            if ':' in stripped and not stripped.startswith(' '):
                # Save previous parameter description
                if current_param == param_name and desc_parts:
                    return ' '.join(desc_parts)

                parts = stripped.split(':', 1)
                current_param = parts[0].strip()
                desc_parts = [parts[1].strip()] if len(parts) > 1 else []
            elif current_param == param_name:
                # Continuation of current parameter description
                desc_parts.append(stripped)

    if current_param == param_name and desc_parts:
        return ' '.join(desc_parts)

    return ""