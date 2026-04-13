"""Context manager for Agent sessions"""

from typing import Optional, Any, AsyncIterator, Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import asyncio

from .hooks import HookRegistry, HookContext, HookEvent, HookResult
from .logger import AgentLogger, get_logger
from .exceptions import SessionError, AgentInterruptedError


@dataclass
class SessionState:
    """State of an agent session"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    loop_count: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # Control flags
    interrupted: bool = False
    stop_requested: bool = False


class AgentSession:
    """
    Context manager for agent sessions

    Provides:
    - Session lifecycle management
    - State persistence
    - Interrupt handling
    - Metrics collection

    Usage:
        async with AgentSession(agent) as session:
            result = await session.run("Hello!")

        # Or manually:
        session = AgentSession(agent)
        await session.start()
        try:
            result = await session.run("Hello!")
        finally:
            await session.stop()
    """

    def __init__(
        self,
        agent: "AgentLoop",
        session_id: Optional[str] = None,
        hooks: Optional[HookRegistry] = None,
        logger: Optional[AgentLogger] = None,
    ):
        self._agent = agent
        self._hooks = hooks or HookRegistry()
        self._logger = logger or get_logger()

        self._state = SessionState(
            session_id=session_id or str(uuid.uuid4())
        )

        self._started = False
        self._lock = asyncio.Lock()

    @property
    def session_id(self) -> str:
        return self._state.session_id

    @property
    def loop_count(self) -> int:
        return self._state.loop_count

    @property
    def messages(self) -> list:
        return self._state.messages.copy()

    async def start(self) -> None:
        """Start the session"""
        if self._started:
            raise SessionError("Session already started")

        self._started = True
        self._state.created_at = datetime.now()

        # Trigger start hook
        await self._hooks.trigger(
            HookEvent.AGENT_START,
            HookContext(
                event=HookEvent.AGENT_START,
                session_id=self.session_id
            )
        )

        self._logger.info(f"Session started: {self.session_id}")

    async def stop(self, save: bool = True) -> Dict[str, Any]:
        """Stop the session and optionally save state"""
        if not self._started:
            return {}

        self._started = False

        # Trigger stop hook
        await self._hooks.trigger(
            HookEvent.AGENT_STOP,
            HookContext(
                event=HookEvent.AGENT_STOP,
                session_id=self.session_id,
                loop_count=self._state.loop_count
            )
        )

        # Get summary
        summary = self.get_summary()

        self._logger.info(
            f"Session stopped: {self.session_id}",
            loops=self._state.loop_count,
            tokens=self._state.total_tokens,
            tool_calls=self._state.total_tool_calls
        )

        return summary

    def interrupt(self) -> None:
        """Request session interruption"""
        self._state.interrupted = True
        self._logger.warning(f"Session interrupted: {self.session_id}")

    def get_summary(self) -> Dict[str, Any]:
        """Get session summary"""
        duration = (datetime.now() - self._state.created_at).total_seconds()

        return {
            "session_id": self.session_id,
            "duration_seconds": duration,
            "loop_count": self._state.loop_count,
            "total_tokens": self._state.total_tokens,
            "total_tool_calls": self._state.total_tool_calls,
            "message_count": len(self._state.messages),
        }

    async def run(self, user_input: str) -> Any:
        """
        Run the agent with user input

        Raises AgentInterruptedError if session was interrupted
        """
        if not self._started:
            await self.start()

        # Check for interruption
        if self._state.interrupted:
            raise AgentInterruptedError("Session was interrupted")

        # Run the agent
        result = await self._agent.run(user_input)

        # Update state from actual agent metrics.
        self._state.loop_count = self._agent.metrics.total_loops
        self._state.total_tokens = self._agent.metrics.total_tokens
        self._state.total_tool_calls = self._agent.metrics.tool_calls

        return result

    async def __aenter__(self) -> "AgentSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.stop(save=True)
        return False


class SessionManager:
    """
    Manager for multiple sessions

    Useful for:
    - Multi-user applications
    - Session persistence
    - Session recovery
    """

    def __init__(self, agent_factory: Callable[[], "AgentLoop"]):
        """
        Initialize session manager

        Args:
            agent_factory: Function to create new agent instances
        """
        self._agent_factory = agent_factory
        self._sessions: Dict[str, AgentSession] = {}

    async def create_session(
        self,
        session_id: Optional[str] = None
    ) -> AgentSession:
        """Create a new session"""
        agent = self._agent_factory()
        session = AgentSession(agent, session_id)
        await session.start()
        self._sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Get an existing session"""
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Close and remove a session"""
        session = self._sessions.pop(session_id, None)
        if session:
            return await session.stop()
        return None

    async def close_all(self) -> Dict[str, Dict[str, Any]]:
        """Close all sessions"""
        results = {}
        for session_id, session in list(self._sessions.items()):
            results[session_id] = await session.stop()
        self._sessions.clear()
        return results

    def list_sessions(self) -> list[str]:
        """List all active session IDs"""
        return list(self._sessions.keys())

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Get summaries for all sessions"""
        return {
            sid: session.get_summary()
            for sid, session in self._sessions.items()
        }