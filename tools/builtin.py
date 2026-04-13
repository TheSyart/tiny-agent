"""Built-in tools registry - aggregates tools defined in sibling modules.

Tool set is modeled after Claude Code's core tools:
- Read/Write/Edit (file_read, file_write, file_edit)
- Bash (shell_exec)
- Grep (grep)
- Glob (glob_files)
- WebSearch/WebFetch (web_search, web_fetch)
"""

from .registry import ToolRegistry
from .web import web_search, web_fetch
from .file import file_read, file_write, file_edit
from .shell import shell_exec
from .search import grep, glob_files


def get_builtin_tools() -> ToolRegistry:
    """Return a ``ToolRegistry`` populated with all built-in tools."""
    registry = ToolRegistry()
    for tool in (
        web_search,
        web_fetch,
        file_read,
        file_write,
        file_edit,
        shell_exec,
        grep,
        glob_files,
    ):
        registry.register(tool)
    return registry


__all__ = [
    "get_builtin_tools",
    "web_search",
    "web_fetch",
    "file_read",
    "file_write",
    "file_edit",
    "shell_exec",
    "grep",
    "glob_files",
]
