"""Safety Manager - Multi-level security system

Note: ``blocked_commands`` is a best-effort guard against accidental
destructive shell commands. It is **not** a security boundary — a determined
adversary can trivially craft equivalents (eval, base64-decoded commands,
alternative tools). For real isolation, run the agent inside a container,
a chroot, or use seccomp/apparmor profiles.
"""

import shlex
from enum import Enum
from typing import Callable, Awaitable, Optional, List, Any
from dataclasses import dataclass, field
from pathlib import Path


class SafetyMode(Enum):
    """Safety mode levels"""
    SANDBOX = "sandbox"      # Restrict file/command access
    CONFIRM = "confirm"      # Ask user for dangerous operations
    TRUST = "trust"          # Allow all operations


@dataclass
class SafetyConfig:
    """Safety configuration"""
    mode: SafetyMode = SafetyMode.CONFIRM
    max_loops: int = 50
    allowed_dirs: List[str] = field(default_factory=list)
    blocked_commands: List[str] = field(default_factory=list)
    dangerous_tools: List[str] = field(default_factory=lambda: [
        "shell_exec",
        "file_write",
        "file_edit",
    ])

    @classmethod
    def trust_all(cls) -> "SafetyConfig":
        """Create a config that trusts everything"""
        return cls(mode=SafetyMode.TRUST)

    @classmethod
    def sandbox_mode(cls, allowed_dirs: List[str]) -> "SafetyConfig":
        """Create a sandbox config"""
        return cls(
            mode=SafetyMode.SANDBOX,
            allowed_dirs=allowed_dirs,
            blocked_commands=["rm -rf", "sudo", "mkfs", "dd if="],
        )


class SafetyManager:
    """
    Safety Manager

    Provides multi-level security for tool execution.
    """

    def __init__(self, config: Optional[SafetyConfig] = None):
        """
        Initialize safety manager

        Args:
            config: Safety configuration
        """
        self.config = config or SafetyConfig()
        self._confirmation_callback: Optional[Callable[[Any], Awaitable[bool]]] = None

    def set_confirmation_callback(
        self,
        callback: Callable[[Any], Awaitable[bool]]
    ) -> None:
        """
        Set callback for user confirmation

        The callback receives the tool use info and should return True to allow.
        """
        self._confirmation_callback = callback

    async def check(self, tool_use: Any) -> str:
        """
        Check if a tool call is allowed

        Args:
            tool_use: ToolUseBlock with name and input

        Returns:
            "allow": Allow execution
            "deny": Deny execution
            "confirm": Need user confirmation
        """
        tool_name = tool_use.name

        # Trust mode - allow everything
        if self.config.mode == SafetyMode.TRUST:
            return "allow"

        # Sandbox mode - check restrictions
        if self.config.mode == SafetyMode.SANDBOX:
            return self._check_sandbox(tool_use)

        # Confirm mode - check if dangerous
        if self.config.mode == SafetyMode.CONFIRM:
            if self._is_dangerous(tool_name):
                return "confirm"
            return "allow"

        return "allow"

    def _check_sandbox(self, tool_use: Any) -> str:
        """Check against sandbox restrictions"""
        tool_name = tool_use.name
        tool_input = tool_use.input or {}

        # Check file operations
        if tool_name in ["file_read", "file_write", "file_edit"]:
            path = tool_input.get("path", "")
            if path and not self._is_path_allowed(path):
                return "deny"

        # Check command execution
        if tool_name == "shell_exec":
            command = tool_input.get("command", "")
            if self._is_command_blocked(command):
                return "deny"

        # Still need confirmation for dangerous tools in sandbox mode
        if self._is_dangerous(tool_name):
            return "confirm"

        return "allow"

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed directories.

        Uses ``Path.is_relative_to`` so that ``/home/u/workspace`` does not
        accidentally allow ``/home/u/workspace-evil/...`` via string prefix
        matching.
        """
        if not self.config.allowed_dirs:
            return True  # No restrictions if not configured

        try:
            abs_path = Path(path).expanduser().resolve()
        except Exception:
            return False

        for allowed_dir in self.config.allowed_dirs:
            try:
                allowed_path = Path(allowed_dir).expanduser().resolve()
            except Exception:
                continue
            try:
                if abs_path == allowed_path or abs_path.is_relative_to(allowed_path):
                    return True
            except AttributeError:
                # Python < 3.9 fallback
                try:
                    abs_path.relative_to(allowed_path)
                    return True
                except ValueError:
                    continue

        return False

    def _is_command_blocked(self, command: str) -> bool:
        """Check if a command matches a blocked pattern.

        Tokenizes via ``shlex`` and checks whether any blocked pattern is a
        token-level subsequence of the command (e.g. ``rm -rf`` matches
        ``rm -rf /tmp/x`` but not ``echo "rm -rf"``). Falls back to a
        conservative substring check on parse failure.
        """
        if not self.config.blocked_commands:
            return False

        try:
            tokens = shlex.split(command, comments=False, posix=True)
        except ValueError:
            # Unbalanced quotes etc. — treat as suspicious, use substring.
            lowered = command.lower()
            return any(b.lower() in lowered for b in self.config.blocked_commands)

        lowered_tokens = [t.lower() for t in tokens]
        for blocked in self.config.blocked_commands:
            try:
                blocked_tokens = [t.lower() for t in shlex.split(blocked)]
            except ValueError:
                blocked_tokens = [blocked.lower()]

            if not blocked_tokens:
                continue

            n = len(blocked_tokens)
            for i in range(len(lowered_tokens) - n + 1):
                if lowered_tokens[i : i + n] == blocked_tokens:
                    return True

        return False

    def _is_dangerous(self, tool_name: str) -> bool:
        """Check if a tool is in the dangerous list"""
        return tool_name in self.config.dangerous_tools

    async def wait_confirmation(self, tool_use: Any) -> bool:
        """
        Wait for user confirmation

        Returns True if user allows the operation
        """
        if self._confirmation_callback:
            return await self._confirmation_callback(tool_use)

        # Default: deny if no callback
        return False

    def get_config_summary(self) -> dict:
        """Get a summary of the current safety config"""
        return {
            "mode": self.config.mode.value,
            "max_loops": self.config.max_loops,
            "allowed_dirs": self.config.allowed_dirs,
            "blocked_commands": self.config.blocked_commands,
            "dangerous_tools": self.config.dangerous_tools,
        }