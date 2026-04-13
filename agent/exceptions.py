"""Exception hierarchy for Tiny-Agent"""

from typing import Optional, Any


class TinyAgentError(Exception):
    """Base exception for Tiny-Agent"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


# LLM Errors
class LLMError(TinyAgentError):
    """Base LLM error"""
    pass


class LLMConnectionError(LLMError):
    """Failed to connect to LLM API"""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, {"retry_after": retry_after})
        self.retry_after = retry_after


class LLMAuthenticationError(LLMError):
    """Authentication failed"""
    pass


class LLMModelNotFoundError(LLMError):
    """Model not found"""
    pass


class LLMResponseError(LLMError):
    """Invalid response from LLM"""
    pass


# Tool Errors
class ToolError(TinyAgentError):
    """Base tool error"""
    pass


class ToolNotFoundError(ToolError):
    """Tool not found in registry"""
    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", {"tool_name": tool_name})


class ToolExecutionError(ToolError):
    """Tool execution failed"""
    def __init__(self, tool_name: str, error: Exception):
        super().__init__(
            f"Tool execution failed: {tool_name}",
            {"tool_name": tool_name, "error": str(error)}
        )
        self.original_error = error


class ToolValidationError(ToolError):
    """Tool input validation failed"""
    pass


# Safety Errors
class SafetyError(TinyAgentError):
    """Base safety error"""
    pass


class PermissionDeniedError(SafetyError):
    """Operation denied by safety policy"""
    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Permission denied for tool: {tool_name}",
            {"tool_name": tool_name, "reason": reason}
        )


class SandboxViolationError(SafetyError):
    """Sandbox restriction violated"""
    def __init__(self, violation_type: str, details: str):
        super().__init__(
            f"Sandbox violation: {violation_type}",
            {"violation_type": violation_type, "details": details}
        )


# Memory Errors
class MemoryError(TinyAgentError):
    """Base memory error"""
    pass


class MemoryOverflowError(MemoryError):
    """Memory limit exceeded"""
    pass


class PersistenceError(MemoryError):
    """Failed to persist memory"""
    pass


# Agent Errors
class AgentError(TinyAgentError):
    """Base agent error"""
    pass


class MaxIterationsError(AgentError):
    """Maximum iterations reached"""
    def __init__(self, max_iterations: int):
        super().__init__(
            f"Maximum iterations reached: {max_iterations}",
            {"max_iterations": max_iterations}
        )


class AgentInterruptedError(AgentError):
    """Agent was interrupted"""
    pass


class SessionError(AgentError):
    """Session management error"""
    pass


# MCP Errors
class MCPError(TinyAgentError):
    """Base MCP error"""
    pass


class MCPConnectionError(MCPError):
    """Failed to connect to MCP server"""
    pass


class MCPToolError(MCPError):
    """MCP tool execution failed"""
    pass


# Configuration Errors
class ConfigError(TinyAgentError):
    """Configuration error"""
    pass


class ConfigValidationError(ConfigError):
    """Configuration validation failed"""
    def __init__(self, field: str, message: str):
        super().__init__(
            f"Config validation failed for '{field}': {message}",
            {"field": field}
        )