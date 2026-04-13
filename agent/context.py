"""ToolUseContext — shared execution context passed to every tool.

Inspired by Claude Code's ToolUseContext pattern: each tool receives a
context object carrying cancellation signals, file-state tracking, and
session metadata.  This enables cooperative cancellation, stale-file
detection, and sub-agent isolation without coupling tools to the agent loop.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import AgentInterruptedError
from .file_state import FileStateCache


@dataclass
class ToolUseContext:
    """Execution context threaded through every tool invocation.

    Attributes:
        abort_event: Cooperative cancellation signal.  Tools should call
            :meth:`check_abort` at safe points to honour interrupt requests.
        read_file_state: Tracks which files have been read and their mtime
            at read time, enabling stale-content warnings.
        session_id: Current session identifier (may be ``None``).
        agent_id: Identifier of the agent that owns this context.
        loop_count: Current iteration of the agent loop.
    """

    abort_event: asyncio.Event
    read_file_state: FileStateCache = field(default_factory=FileStateCache)
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    loop_count: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def check_abort(self) -> None:
        """Raise :class:`AgentInterruptedError` if abort was requested.

        Tools performing long-running work should call this periodically so
        that an ``interrupt()`` on the agent loop propagates promptly.
        """
        if self.abort_event.is_set():
            raise AgentInterruptedError("Tool execution aborted")

    def clone(self) -> "ToolUseContext":
        """Create an isolated copy suitable for a sub-agent.

        The clone shares the *same* ``abort_event`` (parent interrupt
        propagates to children) but gets an independent file-state cache.
        """
        return ToolUseContext(
            abort_event=self.abort_event,
            read_file_state=self.read_file_state.clone(),
            session_id=self.session_id,
            agent_id=self.agent_id,
            loop_count=self.loop_count,
        )
