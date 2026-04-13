"""
Configuration management for Tiny-Agent

Supports:
- YAML configuration files
- Environment variables
- Validation
- Default values
- Nested configuration
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Optional, Dict, List, Union
from dataclasses import dataclass, field, asdict
import logging

from agent.exceptions import ConfigError, ConfigValidationError
from agent.logger import LogLevel


def _get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default"""
    value = os.getenv(key, default)
    if required and value is None:
        raise ConfigValidationError(key, "is required but not set")
    return value


def _expand_path(path: str) -> str:
    """Expand ~ and environment variables in path"""
    return os.path.expanduser(os.path.expandvars(path))


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` / ``${VAR:-default}`` in strings.

    - If the whole string is a single placeholder and the variable is unset
      (no default), return ``None`` so downstream ``__post_init__`` env
      fallbacks still kick in.
    - Otherwise, substitute inline and leave unmatched text as-is.
    """
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if not isinstance(value, str):
        return value

    # Whole-string placeholder → preserve None semantics when unset.
    whole = _ENV_PATTERN.fullmatch(value)
    if whole is not None:
        var, default = whole.group(1), whole.group(2)
        env_val = os.environ.get(var)
        if env_val is not None:
            return env_val
        return default if default is not None else None

    def _sub(match: "re.Match[str]") -> str:
        var, default = match.group(1), match.group(2)
        env_val = os.environ.get(var)
        if env_val is not None:
            return env_val
        return default if default is not None else ""

    return _ENV_PATTERN.sub(_sub, value)


@dataclass
class LLMConfig:
    """LLM configuration"""
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 1.0
    timeout: int = 120  # seconds

    def __post_init__(self):
        # Load from environment if not set
        if self.base_url is None:
            self.base_url = _get_env("ANTHROPIC_BASE_URL")
        if self.api_key is None:
            self.api_key = _get_env("ANTHROPIC_API_KEY")
        model_from_env = _get_env("MODEL_ID")
        if model_from_env:
            self.model = model_from_env

    def validate(self) -> None:
        """Validate LLM configuration"""
        if self.api_key is None:
            raise ConfigValidationError("api_key", "API key is required")
        if self.max_tokens < 1:
            raise ConfigValidationError("max_tokens", "must be positive")
        if not 0 <= self.temperature <= 2:
            raise ConfigValidationError("temperature", "must be between 0 and 2")


@dataclass
class AgentLoopConfig:
    """Agent loop configuration"""
    max_loops: int = 50
    max_tokens: int = 4096
    system_prompt: Optional[str] = None  # None means use prompts/tiny.md
    verbose: bool = False
    stream: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0
    max_budget_tokens: Optional[int] = None

    def validate(self) -> None:
        if self.max_loops < 1:
            raise ConfigValidationError("max_loops", "must be positive")
        if self.max_retries < 0:
            raise ConfigValidationError("max_retries", "must be non-negative")


@dataclass
class MemoryCompressionConfig:
    """Settings for LLM-based memory compression"""
    enabled: bool = True
    trigger_threshold: int = 60  # fallback: compress at this many messages
    keep_recent: int = 20        # preserve tail N messages verbatim
    target_summary_tokens: int = 500
    trigger_ratio: float = 0.70  # compress when estimated tokens >= max_tokens * ratio


@dataclass
class MemoryArchiveConfig:
    """Settings for persistent session archive"""
    enabled: bool = True
    auto_archive_on_clear: bool = True


@dataclass
class MemoryConfig:
    """Memory configuration"""
    type: str = "simple"  # simple or vector
    max_messages: int = 100
    storage_path: str = "./data/memory"
    persist: bool = True

    # Vector store options
    vector_db_path: str = "./data/chroma"
    collection_name: str = "agent_memory"

    # New: compression & archive
    compression: MemoryCompressionConfig = field(default_factory=MemoryCompressionConfig)
    archive: MemoryArchiveConfig = field(default_factory=MemoryArchiveConfig)

    def __post_init__(self):
        self.storage_path = _expand_path(self.storage_path)
        self.vector_db_path = _expand_path(self.vector_db_path)

    def validate(self) -> None:
        if self.type not in ("simple", "vector"):
            raise ConfigValidationError("type", "must be 'simple' or 'vector'")
        if self.compression.trigger_threshold < self.compression.keep_recent + 2:
            raise ConfigValidationError(
                "compression.trigger_threshold",
                "must be greater than keep_recent + 2",
            )


@dataclass
class SafetyModeConfig:
    """Safety mode configuration"""
    allowed_dirs: List[str] = field(default_factory=list)
    blocked_commands: List[str] = field(default_factory=list)
    dangerous_tools: List[str] = field(default_factory=lambda: [
        "shell_exec", "file_write", "file_edit"
    ])

    def __post_init__(self):
        # Expand paths
        self.allowed_dirs = [_expand_path(p) for p in self.allowed_dirs]


@dataclass
class SafetyConfig:
    """Safety configuration"""
    mode: str = "confirm"  # sandbox, confirm, trust
    sandbox: SafetyModeConfig = field(default_factory=SafetyModeConfig)
    confirm: SafetyModeConfig = field(default_factory=SafetyModeConfig)
    max_loops: int = 50
    timeout: int = 300

    def validate(self) -> None:
        if self.mode not in ("sandbox", "confirm", "trust"):
            raise ConfigValidationError("mode", "must be 'sandbox', 'confirm', or 'trust'")

    @classmethod
    def from_dict(cls, data: dict) -> "SafetyConfig":
        """Create from dictionary"""
        sandbox_data = data.get("sandbox", {})
        confirm_data = data.get("confirm", {})

        return cls(
            mode=data.get("mode", "confirm"),
            sandbox=SafetyModeConfig(**sandbox_data) if sandbox_data else SafetyModeConfig(),
            confirm=SafetyModeConfig(**confirm_data) if confirm_data else SafetyModeConfig(),
            max_loops=data.get("max_loops", 50),
            timeout=data.get("timeout", 300),
        )


@dataclass
class MCPServerConfig:
    """Single MCP server configuration"""
    name: str
    command: str
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    enabled: bool = True


@dataclass
class MCPConfig:
    """MCP configuration"""
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)


@dataclass
class SkillsConfig:
    """Skills configuration"""
    auto_discover: bool = True
    directories: List[str] = field(default_factory=lambda: ["./skills/builtin"])

    def __post_init__(self):
        self.directories = [_expand_path(p) for p in self.directories]


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "info"
    json_format: bool = False
    file: Optional[str] = None

    def validate(self) -> None:
        valid_levels = ("debug", "info", "warning", "error", "critical")
        if self.level.lower() not in valid_levels:
            raise ConfigValidationError("level", f"must be one of {valid_levels}")

    def get_log_level(self) -> LogLevel:
        """Convert string to LogLevel"""
        return LogLevel(self.level.lower())


@dataclass
class WebUIConfig:
    """Web UI configuration"""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    def validate(self) -> None:
        if not (1 <= self.port <= 65535):
            raise ConfigValidationError("port", "must be between 1 and 65535")


@dataclass
class Config:
    """Main configuration for Tiny-Agent"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentLoopConfig = field(default_factory=AgentLoopConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    webui: WebUIConfig = field(default_factory=WebUIConfig)

    def validate(self) -> None:
        """Validate all configuration"""
        self.llm.validate()
        self.agent.validate()
        self.memory.validate()
        self.safety.validate()
        self.logging.validate()
        self.webui.validate()

    @classmethod
    def from_yaml(cls, path: str, validate: bool = True) -> "Config":
        """Load configuration from YAML file"""
        config_path = Path(path)

        if not config_path.exists():
            if validate:
                logging.getLogger("tiny-agent").warning(
                    f"Config file not found: {path}, using defaults"
                )
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Interpolate ${VAR} placeholders before building dataclasses so that
        # __post_init__ env fallbacks see either a real value or None.
        data = _interpolate_env(data)

        config = cls.from_dict(data)

        if validate:
            config.validate()

        return config

    @classmethod
    def from_dict(cls, data: Dict) -> "Config":
        """Create configuration from dictionary"""
        llm_data = data.get("llm", {})
        agent_data = data.get("agent", {})
        memory_data = data.get("memory", {})
        safety_data = data.get("safety", {})
        mcp_data = data.get("mcp", {})
        skills_data = data.get("skills", {})
        logging_data = data.get("logging", {})
        webui_data = data.get("webui", {})

        # Parse MCP servers
        mcp_servers = {}
        for name, server_data in mcp_data.get("servers", {}).items():
            mcp_servers[name] = MCPServerConfig(
                name=name,
                command=server_data.get("command", ""),
                args=server_data.get("args"),
                env=server_data.get("env"),
                enabled=server_data.get("enabled", True)
            )

        # After ${VAR} interpolation, an unset env var becomes None. Use
        # ``or default`` (instead of ``dict.get(k, default)``) for fields
        # that must have a real value, so None doesn't overwrite the default.
        return cls(
            llm=LLMConfig(
                base_url=llm_data.get("base_url"),
                api_key=llm_data.get("api_key"),
                model=llm_data.get("model") or "claude-sonnet-4-20250514",
                max_tokens=llm_data.get("max_tokens") or 4096,
                temperature=(
                    llm_data["temperature"]
                    if "temperature" in llm_data and llm_data["temperature"] is not None
                    else 1.0
                ),
                timeout=llm_data.get("timeout") or 120,
            ),
            agent=AgentLoopConfig(
                max_loops=agent_data.get("max_loops", 50),
                max_tokens=agent_data.get("max_tokens", 4096),
                system_prompt=agent_data.get("system_prompt"),  # None if not set
                verbose=agent_data.get("verbose", False),
                stream=agent_data.get("stream", True),
                max_retries=agent_data.get("max_retries", 3),
                retry_delay=agent_data.get("retry_delay", 1.0),
                max_budget_tokens=agent_data.get("max_budget_tokens"),
            ),
            memory=MemoryConfig(
                type=memory_data.get("type", "simple"),
                max_messages=memory_data.get("max_messages", 100),
                storage_path=memory_data.get("storage_path", "./data/memory"),
                persist=memory_data.get("persist", True),
                vector_db_path=memory_data.get("vector_db_path", "./data/chroma"),
                collection_name=memory_data.get("collection_name", "agent_memory"),
                compression=MemoryCompressionConfig(
                    **(memory_data.get("compression") or {})
                ),
                archive=MemoryArchiveConfig(
                    **(memory_data.get("archive") or {})
                ),
            ),
            safety=SafetyConfig.from_dict(safety_data),
            mcp=MCPConfig(servers=mcp_servers),
            skills=SkillsConfig(
                auto_discover=skills_data.get("auto_discover", True),
                directories=skills_data.get("directories", ["./skills/builtin"]),
            ),
            logging=LoggingConfig(
                level=logging_data.get("level", "info"),
                json_format=logging_data.get("json_format", False),
                file=logging_data.get("file"),
            ),
            webui=WebUIConfig(
                enabled=webui_data.get("enabled", True),
                host=webui_data.get("host", "127.0.0.1"),
                port=webui_data.get("port", 8000),
                debug=webui_data.get("debug", False),
                cors_origins=webui_data.get("cors_origins", ["*"]),
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        def _convert(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: _convert(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [_convert(v) for v in obj]
            elif isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            return obj

        return _convert(self)

    def save_yaml(self, path: str) -> None:
        """Save configuration to YAML file"""
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)


def load_config(
    config_path: Optional[str] = None,
    validate: bool = True
) -> Config:
    """
    Load configuration from file or defaults

    Priority:
    1. Specified config path
    2. ./config.yaml
    3. ~/.tiny-agent/config.yaml
    4. Environment variables
    5. Defaults
    """
    paths_to_try = []

    if config_path:
        paths_to_try.append(config_path)

    paths_to_try.extend([
        "./config.yaml",
        "./tiny-agent.yaml",
        str(Path.home() / ".tiny-agent" / "config.yaml"),
    ])

    for path in paths_to_try:
        if Path(path).exists():
            return Config.from_yaml(path, validate)

    # No config file found, use defaults
    config = Config()
    if validate:
        try:
            config.validate()
        except ConfigValidationError as e:
            logging.getLogger("tiny-agent").warning(
                f"Config validation warning: {e}"
            )

    return config