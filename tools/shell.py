"""Built-in tool for shell command execution"""

import asyncio
import os
import signal
from typing import Optional
from .base import tool


@tool(is_dangerous=True)
async def shell_exec(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None
) -> str:
    """
    Execute a shell command

    Use with caution - this runs commands on the system.

    Args:
        command: The shell command to execute
        timeout: Timeout in seconds (default: 30)
        cwd: Working directory for the command
    """
    process = None
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            # Use process group so we can kill the entire tree on timeout.
            preexec_fn=os.setsid,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Kill entire process group to prevent zombies.
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
            # Reap the process to avoid zombie.
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            return f"Command timed out after {timeout} seconds"

        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')

        result_parts = []
        if stdout_text:
            result_parts.append(f"stdout:\n{stdout_text}")
        if stderr_text:
            result_parts.append(f"stderr:\n{stderr_text}")
        result_parts.append(f"Exit code: {process.returncode}")

        output = "\n\n".join(result_parts)

        max_length = 5000
        if len(output) > max_length:
            output = output[:max_length] + "\n\n... (output truncated)"

        return output

    except Exception as e:
        # Best-effort cleanup if process was created but an unexpected error
        # occurred before communicate() finished.
        if process and process.returncode is None:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
        return f"Error executing command: {str(e)}"


