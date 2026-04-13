"""Agent module for Tiny-Agent"""

from .types import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    Message,
    LLMResponse,
    ToolResult,
)
from .loop import AgentLoop, AgentConfig, AgentState, AgentMetrics
from .llm_client import LLMClient
from .exceptions import (
    TinyAgentError,
    LLMError,
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    SafetyError,
    PermissionDeniedError,
    AgentError,
    MaxIterationsError,
    AgentInterruptedError,
)
from .logger import AgentLogger, LogLevel, get_logger, configure_logging
from .hooks import (
    HookEvent,
    HookContext,
    HookResult,
    HookRegistry,
    HookHandler,
    get_hook_registry,
)
from .session import AgentSession, SessionManager, SessionState

__all__ = [
    # Types
    "ContentBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "Message",
    "LLMResponse",
    "ToolResult",
    # Agent
    "AgentLoop",
    "AgentConfig",
    "AgentState",
    "AgentMetrics",
    "LLMClient",
    # Exceptions
    "TinyAgentError",
    "LLMError",
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "SafetyError",
    "PermissionDeniedError",
    "AgentError",
    "MaxIterationsError",
    "AgentInterruptedError",
    # Logging
    "AgentLogger",
    "LogLevel",
    "get_logger",
    "configure_logging",
    # Hooks
    "HookEvent",
    "HookContext",
    "HookResult",
    "HookRegistry",
    "HookHandler",
    "get_hook_registry",
    # Session
    "AgentSession",
    "SessionManager",
    "SessionState",
]