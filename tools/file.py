"""Built-in tools for file operations"""

from pathlib import Path
from typing import Optional
from .base import tool


@tool(is_concurrency_safe=True)
async def file_read(path: str) -> str:
    """
    Read the contents of a file

    Args:
        path: Path to the file to read
    """
    try:
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return f"Error: File not found: {path}"

        if not file_path.is_file():
            return f"Error: Not a file: {path}"

        # Try to read as text
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return f"Error: Binary file (cannot read as text): {path}"

        # Truncate if too large
        max_size = 100000  # 100KB
        if len(content) > max_size:
            content = content[:max_size] + "\n\n... (file truncated)"

        return content

    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool(is_dangerous=True)
async def file_write(path: str, content: str) -> str:
    """
    Write content to a file

    This will create the file if it doesn't exist, or overwrite it if it does.

    Args:
        path: Path to the file to write
        content: Content to write to the file
    """
    try:
        file_path = Path(path).expanduser().resolve()

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding='utf-8')

        return f"Successfully wrote {len(content)} characters to {path}"

    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool(is_dangerous=True)
async def file_edit(path: str, old_text: str, new_text: str) -> str:
    """
    Edit a file by replacing text

    Finds all occurrences of old_text and replaces them with new_text.

    Args:
        path: Path to the file to edit
        old_text: Text to find and replace
        new_text: Text to replace with
    """
    try:
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return f"Error: File not found: {path}"

        content = file_path.read_text(encoding='utf-8')

        if old_text not in content:
            return f"Error: Text not found in file: {old_text[:50]}..."

        new_content = content.replace(old_text, new_text)
        file_path.write_text(new_content, encoding='utf-8')

        count = content.count(old_text)
        return f"Successfully replaced {count} occurrence(s) in {path}"

    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error: {str(e)}"


