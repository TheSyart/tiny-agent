"""Built-in search tools: Grep (content search) and Glob (file pattern matching).

Modeled after Claude Code's Grep/Glob tools. Grep prefers ripgrep when
available and falls back to a pure-Python implementation; Glob uses
``pathlib`` recursive matching.
"""

import asyncio
import re
import shutil
from pathlib import Path
from typing import Optional

from .base import tool


@tool
async def grep(
    pattern: str,
    path: str = ".",
    glob: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = 100,
) -> str:
    """
    Search file contents for a regex pattern (ripgrep-style).

    Args:
        pattern: Regular expression to search for
        path: File or directory to search in (default: current directory)
        glob: Optional glob filter, e.g. "*.py" or "**/*.ts"
        case_insensitive: Case-insensitive match
        max_results: Maximum number of matching lines to return
    """
    search_root = Path(path).expanduser().resolve()
    if not search_root.exists():
        return f"Error: Path not found: {path}"

    rg = shutil.which("rg")
    if rg:
        args = [rg, "--line-number", "--no-heading", "--color=never"]
        if case_insensitive:
            args.append("-i")
        if glob:
            args += ["--glob", glob]
        args += ["--max-count", str(max_results), pattern, str(search_root)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out = stdout.decode("utf-8", errors="replace").strip()
            if not out:
                return f"No matches for '{pattern}'"
            lines = out.splitlines()
            if len(lines) > max_results:
                lines = lines[:max_results] + [f"... (truncated, showing {max_results} of {len(lines)} matches)"]
            return "\n".join(lines)
        except asyncio.TimeoutError:
            return "Error: grep timed out after 30s"
        except Exception as e:
            return f"Error: {str(e)}"

    # Fallback: pure Python
    try:
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: invalid regex: {e}"

    matches: list[str] = []
    files: list[Path]
    if search_root.is_file():
        files = [search_root]
    else:
        pat = glob or "**/*"
        files = [f for f in search_root.glob(pat) if f.is_file()]

    for f in files:
        if len(matches) >= max_results:
            break
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if regex.search(line):
                        matches.append(f"{f}:{lineno}:{line.rstrip()}")
                        if len(matches) >= max_results:
                            break
        except (OSError, UnicodeDecodeError):
            continue

    if not matches:
        return f"No matches for '{pattern}'"
    return "\n".join(matches)


@tool
async def glob_files(
    pattern: str,
    path: str = ".",
    max_results: int = 200,
) -> str:
    """
    Find files matching a glob pattern (e.g. "**/*.py", "src/**/*.ts").

    Results are sorted by modification time (most recent first).

    Args:
        pattern: Glob pattern to match against file paths
        path: Root directory for the search (default: current directory)
        max_results: Maximum number of paths to return
    """
    try:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return f"Error: Path not found: {path}"
        if not root.is_dir():
            return f"Error: Not a directory: {path}"

        items = [p for p in root.glob(pattern) if p.is_file()]
        items.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if not items:
            return f"No files matching '{pattern}' in {path}"

        truncated = len(items) > max_results
        items = items[:max_results]
        lines = [str(p) for p in items]
        if truncated:
            lines.append(f"... (truncated, showing {max_results} of {len(items)}+ results)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"
