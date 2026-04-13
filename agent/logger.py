"""Structured logging system for Tiny-Agent"""

import logging
import sys
from typing import Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
import json


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogContext:
    """Context for structured logging"""
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    loop_count: int = 0
    tool_name: Optional[str] = None
    user_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context if available
        if hasattr(record, "context") and record.context:
            log_data["context"] = record.context

        # Add extra fields
        if hasattr(record, "extra_data") and record.extra_data:
            log_data["data"] = record.extra_data

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter"""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        parts = [f"{color}[{record.levelname:8}]{self.RESET} {timestamp}"]

        # Add context
        if hasattr(record, "context") and record.context:
            ctx = record.context
            if ctx.tool_name:
                parts.append(f"[{ctx.tool_name}]")
            if ctx.loop_count > 0:
                parts.append(f"(loop {ctx.loop_count})")

        parts.append(f"{record.name}: {record.getMessage()}")

        return " ".join(parts)


class AgentLogger:
    """
    Logger for Tiny-Agent with structured logging support

    Usage:
        logger = AgentLogger("tiny-agent")
        logger.info("Starting agent", context=LogContext(session_id="abc123"))
        logger.tool_call("bash", {"command": "ls -la"})
    """

    def __init__(
        self,
        name: str = "tiny-agent",
        level: LogLevel = LogLevel.INFO,
        json_format: bool = False
    ):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.value.upper()))

        # Clear existing handlers
        self._logger.handlers.clear()

        # Add handler
        handler = logging.StreamHandler(sys.stderr)
        formatter = StructuredFormatter() if json_format else HumanFormatter()
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

        self._context = LogContext()

    def set_context(self, **kwargs) -> None:
        """Update logging context"""
        for key, value in kwargs.items():
            if hasattr(self._context, key):
                setattr(self._context, key, value)

    def _log(self, level: int, message: str, extra: Optional[dict] = None) -> None:
        """Internal log method"""
        record = self._logger.makeRecord(
            self._logger.name, level, "", 0, message, (), None
        )
        record.context = self._context
        record.extra_data = extra
        self._logger.handle(record)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, kwargs if kwargs else None)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, kwargs if kwargs else None)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, kwargs if kwargs else None)

    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, kwargs if kwargs else None)

    def critical(self, message: str, **kwargs) -> None:
        self._log(logging.CRITICAL, message, kwargs if kwargs else None)

    # Convenience methods for common events
    def llm_request(self, messages_count: int, tools_count: int) -> None:
        """Log LLM request"""
        self.debug(
            f"LLM request: {messages_count} messages, {tools_count} tools",
            messages=messages_count,
            tools=tools_count
        )

    def llm_response(self, stop_reason: str, tokens: Optional[dict] = None) -> None:
        """Log LLM response"""
        self.debug(
            f"LLM response: stop_reason={stop_reason}",
            stop_reason=stop_reason,
            tokens=tokens
        )

    def tool_call(self, tool_name: str, input_data: dict) -> None:
        """Log tool call"""
        old_tool = self._context.tool_name
        self._context.tool_name = tool_name
        self.info(f"Calling tool: {tool_name}", input=input_data)
        self._context.tool_name = old_tool

    def tool_result(self, tool_name: str, success: bool, duration_ms: Optional[float] = None) -> None:
        """Log tool result"""
        status = "success" if success else "failed"
        self.info(
            f"Tool result: {tool_name} ({status})",
            success=success,
            duration_ms=duration_ms
        )

    def loop_start(self, loop_count: int, max_loops: int) -> None:
        """Log loop start"""
        self._context.loop_count = loop_count
        self.debug(f"Starting loop {loop_count}/{max_loops}")

    def loop_end(self, loop_count: int, stop_reason: str) -> None:
        """Log loop end"""
        self.info(f"Agent finished after {loop_count} loops: {stop_reason}")


# Global logger instance
_logger: Optional[AgentLogger] = None


def get_logger(name: str = "tiny-agent") -> AgentLogger:
    """Get or create the global logger"""
    global _logger
    if _logger is None:
        _logger = AgentLogger(name)
    return _logger


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    json_format: bool = False
) -> AgentLogger:
    """Configure global logging"""
    global _logger
    _logger = AgentLogger("tiny-agent", level, json_format)
    return _logger