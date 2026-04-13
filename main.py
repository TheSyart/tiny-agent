#!/usr/bin/env python3
"""
Tiny-Agent - A production-grade AI agent framework

Usage:
    python main.py                    # Run with Web UI
    python main.py --cli              # Run in CLI mode
    python main.py --config my.yaml   # Use custom config
    python main.py --help             # Show help
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from config import load_config, Config
from agent import (
    AgentLoop,
    AgentConfig,
    configure_logging,
    LogLevel,
    HookRegistry,
    AgentSession,
    TinyAgentError,
)
from agent.llm_client import LLMClient
from tools.builtin import get_builtin_tools
from tools.memory_tool import make_memory_recall_tool, make_save_memory_tool
from tools.system_prompt_tool import make_update_prompt_tool
from tools.knowledge_skill_tool import KnowledgeSkillRegistry, make_knowledge_skill_tools
from memory.manager import MemoryManager
from memory.compressor import MemoryCompressor
from safety.manager import SafetyManager, SafetyConfig, SafetyMode
from prompts import get_tiny_config, SystemPromptBuilder

import logging

_startup_log = logging.getLogger("tiny-agent.startup")


def get_default_system_prompt() -> str:
    """Load default system prompt from tiny.md"""
    try:
        return get_tiny_config()
    except Exception as e:
        _startup_log.warning(f"Failed to load tiny.md: {e}")
        return "你是小T，一个友好、高效、可靠的 AI 助手。"


def create_agent(config: Config, hooks: Optional[HookRegistry] = None) -> AgentLoop:
    """Create an agent instance with configuration"""
    # Build system prompt using SystemPromptBuilder.
    # Static sections are stable across turns (cacheable by Anthropic API).
    # Dynamic sections change per session (skills, memory, etc.).
    prompt_builder = SystemPromptBuilder()
    base_prompt = config.agent.system_prompt or get_default_system_prompt()
    prompt_builder.add_static(base_prompt)

    # Create LLM client
    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        temperature=config.llm.temperature,
    )

    # Create tools
    tools = get_builtin_tools()

    # Build optional memory compressor (reuses the same LLM client)
    compressor: Optional[MemoryCompressor] = None
    if config.memory.compression.enabled:
        compressor = MemoryCompressor(
            llm_client=llm,
            trigger_threshold=config.memory.compression.trigger_threshold,
            keep_recent=config.memory.compression.keep_recent,
            target_summary_tokens=config.memory.compression.target_summary_tokens,
            trigger_ratio=config.memory.compression.trigger_ratio,
            max_context_tokens=config.llm.max_tokens,
        )

    # Create memory
    if config.memory.type == "vector":
        memory = MemoryManager.create_with_vector(
            max_messages=config.memory.max_messages,
            persist_directory=config.memory.vector_db_path,
            compressor=compressor,
            archive_enabled=config.memory.archive.enabled,
        )
    else:
        memory = MemoryManager.create_simple(
            max_messages=config.memory.max_messages,
            storage_path=config.memory.storage_path,
            compressor=compressor,
            archive_enabled=config.memory.archive.enabled,
        )

    # Register memory tools
    if config.memory.archive.enabled:
        tools.register(make_memory_recall_tool(memory))
    tools.register(make_save_memory_tool(storage_path=config.memory.storage_path))

    # Create safety manager
    safety_mode = {
        "sandbox": SafetyMode.SANDBOX,
        "confirm": SafetyMode.CONFIRM,
        "trust": SafetyMode.TRUST,
    }.get(config.safety.mode, SafetyMode.CONFIRM)

    safety = SafetyManager(SafetyConfig(
        mode=safety_mode,
        allowed_dirs=config.safety.sandbox.allowed_dirs,
        blocked_commands=config.safety.sandbox.blocked_commands,
        dangerous_tools=config.safety.sandbox.dangerous_tools,
    ))

    # Create agent config — system prompt is built from the builder below
    # (after skills are registered and can contribute dynamic sections).
    agent_config = AgentConfig(
        max_loops=config.agent.max_loops,
        max_tokens=config.agent.max_tokens,
        system_prompt=base_prompt,  # placeholder — overwritten after skills
        verbose=config.agent.verbose,
        stream=config.agent.stream,
        max_tool_concurrency=config.agent.max_tool_concurrency,
    )

    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=safety,
        config=agent_config,
        hooks=hooks,
    )

    # Register update_system_prompt after loop creation (needs loop reference)
    agent.tools.register(make_update_prompt_tool(
        prompt_path="prompts/tiny.md",
        agent_loop=agent,
    ))

    # Register knowledge skill tools (SKILL.md-based on-demand knowledge injection)
    skill_dirs = config.skills.directories if config.skills.directories else []
    knowledge_registry = KnowledgeSkillRegistry(skill_dirs)
    for t in make_knowledge_skill_tools(knowledge_registry):
        tools.register(t)

    # Append available skill descriptions as a dynamic section
    skill_descriptions = knowledge_registry.describe_available()
    if skill_descriptions:
        prompt_builder.add_dynamic(skill_descriptions)

    # Finalize system prompt from the builder
    agent.config.system_prompt = prompt_builder.build()

    # Store builder on agent so callers (e.g. WebUI) can rebuild with
    # additional dynamic sections (memory context, datetime, etc.)
    agent._prompt_builder = prompt_builder  # type: ignore[attr-defined]

    # Expose registry on agent for later reloads (e.g. after creating a new SKILL.md)
    agent._knowledge_registry = knowledge_registry  # type: ignore[attr-defined]

    return agent


async def setup_external_tools(agent: AgentLoop, config: Config) -> None:
    """Wire up MCP servers and skill-provided tools into the agent registry.

    Both are best-effort: failures are logged and swallowed so the agent can
    still boot with the builtin tool set.
    """
    # --- MCP servers ---
    if config.mcp.servers:
        try:
            from mcp.connector import MCPConnector
        except Exception as e:
            _startup_log.warning(f"MCP module unavailable: {e}")
        else:
            connector = MCPConnector()
            for name, server in config.mcp.servers.items():
                if not server.enabled:
                    continue
                try:
                    ok = await connector.add_server(
                        name=name,
                        command=server.command,
                        args=server.args,
                        env=server.env,
                    )
                    if not ok:
                        _startup_log.warning(f"MCP server failed to connect: {name}")
                        continue
                except Exception as e:
                    _startup_log.warning(f"MCP server '{name}' error: {e}")
                    continue
                _startup_log.info(f"MCP server connected: {name}")

            # Expose the connector on the agent for later tool dispatch.
            agent.mcp = connector  # type: ignore[attr-defined]

    # --- Skills ---
    if config.skills.auto_discover and config.skills.directories:
        try:
            from skills.loader import SkillLoader
        except Exception as e:
            _startup_log.warning(f"Skills module unavailable: {e}")
            return

        if not hasattr(agent, '_loaded_skills'):
            agent._loaded_skills = []  # type: ignore[attr-defined]

        for skills_dir in config.skills.directories:
            try:
                loader = SkillLoader(skills_dir)
                loaded = loader.auto_discover()
                if not loaded:
                    continue
                for tool in loader.get_all_tools():
                    try:
                        agent.tools.register(tool)
                    except Exception as e:
                        _startup_log.warning(
                            f"Failed to register skill tool from {skills_dir}: {e}"
                        )
                # Store skill metadata for the UI
                for skill in loader._loaded.values():
                    try:
                        agent._loaded_skills.append({  # type: ignore[attr-defined]
                            "name": skill.info.name,
                            "description": skill.info.description,
                            "version": skill.info.version,
                            "author": skill.info.author,
                            "tags": skill.info.tags,
                            "tools": [t.name for t in skill.get_tools()],
                        })
                    except Exception:
                        pass
                _startup_log.info(
                    f"Loaded {len(loaded)} skill(s) from {skills_dir}: {loaded}"
                )
            except Exception as e:
                _startup_log.warning(
                    f"Skill discovery failed for {skills_dir}: {e}"
                )


async def _cli_confirm(tool_use) -> bool:
    """Ask the user on stdin whether a dangerous tool call may proceed."""
    loop = asyncio.get_running_loop()
    name = getattr(tool_use, "name", "?")
    inp = getattr(tool_use, "input", {})
    prompt = f"\n[confirm] Allow tool '{name}' with input {inp}? [y/N] "

    def _ask() -> str:
        try:
            return input(prompt)
        except EOFError:
            return ""

    answer = (await loop.run_in_executor(None, _ask)).strip().lower()
    return answer in ("y", "yes")


async def run_cli(agent: AgentLoop, config: Config):
    """Run in CLI mode"""
    # Wire up CLI-side confirmation so 'confirm' mode actually works.
    if agent.safety is not None:
        agent.safety.set_confirmation_callback(_cli_confirm)

    await setup_external_tools(agent, config)

    print("=" * 50)
    print("Tiny-Agent CLI")
    print("=" * 50)
    print("Commands: 'exit' to quit, 'clear' to clear history")
    print()

    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "exit":
                print("Goodbye!")
                break

            if user_input.lower() == "clear":
                agent.memory.clear_short_term()
                print("History cleared.")
                continue

            # Run agent
            print()
            async for event_type, data in agent.run_stream(user_input):
                if event_type == "text":
                    print(data, end="", flush=True)
                elif event_type == "tool_call":
                    print(f"\n[🔧 {data['name']}]")
                elif event_type == "tool_result":
                    pass  # Don't print tool results in CLI
                elif event_type == "done":
                    if data.text:
                        print()
                    print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except TinyAgentError as e:
            print(f"\n[Error] {e.message}")
        except Exception as e:
            print(f"\n[Error] {e}")


async def run_webui(agent: AgentLoop, config: Config):
    """Run with Web UI"""
    from webui.app import create_app
    import uvicorn

    await setup_external_tools(agent, config)

    app = create_app(agent, config)

    print(f"\nStarting Tiny-Agent Web UI")
    print(f"URL: http://{config.webui.host}:{config.webui.port}")
    print()

    server_config = uvicorn.Config(
        app,
        host=config.webui.host,
        port=config.webui.port,
        log_level="warning",
    )

    server = uvicorn.Server(server_config)
    await server.serve()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Tiny-Agent - A production-grade AI agent framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                    # Start Web UI
    python main.py --cli              # CLI mode
    python main.py --verbose          # Enable verbose logging
        """
    )

    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--config", type=str, default="config.yaml", help="Config file path")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--log-level", type=str, default="info", help="Log level (debug/info/warning/error)")
    parser.add_argument("--trust", action="store_true", help="Run in trust mode (no safety checks)")

    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config, validate=False)
    except Exception as e:
        print(f"Warning: Failed to load config: {e}")
        config = Config()

    # Override config from args
    if args.verbose:
        config.agent.verbose = True
        config.logging.level = "debug"

    if args.trust:
        config.safety.mode = "trust"

    # Configure logging
    log_level = LogLevel(args.log_level.lower())
    configure_logging(level=log_level, json_format=False)

    # Create agent
    try:
        agent = create_agent(config)
    except Exception as e:
        print(f"Error creating agent: {e}")
        sys.exit(1)

    # Print info
    print("=" * 50)
    print("Tiny-Agent v0.1.0")
    print("=" * 50)
    print(f"Model: {config.llm.model}")
    print(f"Tools: {len(get_builtin_tools().list_tools())} registered")
    print(f"Safety: {config.safety.mode} mode")
    print(f"Memory: {config.memory.type}")
    print("=" * 50)

    # Check API key
    if not config.llm.api_key:
        print("\nError: No API key configured!")
        print("Set ANTHROPIC_API_KEY environment variable or configure in config.yaml")
        sys.exit(1)

    # Run
    if args.cli:
        asyncio.run(run_cli(agent, config))
    else:
        asyncio.run(run_webui(agent, config))


if __name__ == "__main__":
    main()