#!/usr/bin/env python3
"""
Tiny-Agent Example Usage

This demonstrates the production-grade features of the Tiny-Agent framework.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# Core imports
from config import load_config
from agent import (
    AgentLoop,
    AgentConfig,
    AgentLogger,
    LogLevel,
    configure_logging,
    HookRegistry,
    HookEvent,
    HookContext,
    HookResult,
    AgentSession,
    SessionManager,
)
from agent.llm_client import LLMClient
from tools.builtin import get_builtin_tools
from memory.manager import MemoryManager
from safety.manager import SafetyManager, SafetyConfig, SafetyMode


async def example_basic():
    """Example 1: Basic usage"""
    print("\n" + "=" * 60)
    print("Example 1: Basic Agent Usage")
    print("=" * 60)

    config = load_config()

    # Create components
    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
    )

    tools = get_builtin_tools()
    memory = MemoryManager.create_simple(storage_path=config.memory.storage_path)
    safety = SafetyManager(SafetyConfig(mode=SafetyMode.TRUST))

    # Create agent
    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=safety,
        config=AgentConfig(
            max_loops=10,
            system_prompt="You are a helpful assistant. Be concise.",
            verbose=True,
        )
    )

    # Run
    result = await agent.run("What is 2+2?")
    print(f"\nResult: {result.text if hasattr(result, 'text') else result.content}")
    print(f"Metrics: {agent.metrics.to_dict()}")


async def example_with_hooks():
    """Example 2: Using hooks for logging and control"""
    print("\n" + "=" * 60)
    print("Example 2: Hooks System")
    print("=" * 60)

    config = load_config()

    # Create hook registry
    hooks = HookRegistry()

    # Register hooks
    @hooks.on(HookEvent.PRE_TOOL_USE, "shell_exec")
    async def check_dangerous_command(ctx: HookContext) -> HookResult:
        """Block dangerous shell commands"""
        command = ctx.tool_input.get("command", "")
        dangerous = ["rm -rf", "sudo", "mkfs", "dd if="]

        for danger in dangerous:
            if danger in command:
                print(f"[HOOK] Blocked dangerous command: {danger}")
                return HookResult(
                    continue_=False,
                    error_message=f"Dangerous command blocked: {danger}"
                )

        return HookResult()

    @hooks.on(HookEvent.POST_TOOL_USE)
    async def log_tool_result(ctx: HookContext) -> HookResult:
        """Log all tool results"""
        print(f"[HOOK] Tool completed: {ctx.tool_name}")
        return HookResult()

    # Create components
    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
    )

    tools = get_builtin_tools()
    memory = MemoryManager.create_simple()
    safety = SafetyManager(SafetyConfig(mode=SafetyMode.TRUST))

    # Create agent with hooks
    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=safety,
        hooks=hooks,
        config=AgentConfig(max_loops=10),
    )

    # Run
    result = await agent.run("List files in current directory")
    print(f"\nResult: {result.text[:200] if result.text else 'No text'}...")


async def example_streaming():
    """Example 3: Streaming output"""
    print("\n" + "=" * 60)
    print("Example 3: Streaming Output")
    print("=" * 60)

    config = load_config()

    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
    )

    tools = get_builtin_tools()
    memory = MemoryManager.create_simple()
    safety = SafetyManager(SafetyConfig(mode=SafetyMode.TRUST))

    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=safety,
        config=AgentConfig(max_loops=10),
    )

    print("Streaming response:")
    print("-" * 40)

    async for event_type, data in agent.run_stream("Tell me a short joke"):
        if event_type == "text":
            print(data, end="", flush=True)
        elif event_type == "tool_call":
            print(f"\n[Calling tool: {data['name']}]")
        elif event_type == "tool_result":
            print(f"[Tool result received]")
        elif event_type == "done":
            print("\n[Done]")

    print(f"\nMetrics: {agent.metrics.to_dict()}")


async def example_session():
    """Example 4: Session management"""
    print("\n" + "=" * 60)
    print("Example 4: Session Management")
    print("=" * 60)

    config = load_config()

    def create_agent():
        """Factory function to create agent instances"""
        llm = LLMClient(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
            model=config.llm.model,
        )
        tools = get_builtin_tools()
        memory = MemoryManager.create_simple()
        safety = SafetyManager(SafetyConfig(mode=SafetyMode.TRUST))

        return AgentLoop(
            llm_client=llm,
            tools=tools,
            memory=memory,
            safety=safety,
            config=AgentConfig(max_loops=10),
        )

    # Create session manager
    session_manager = SessionManager(create_agent)

    # Create a session
    async with await session_manager.create_session() as session:
        print(f"Session ID: {session.session_id}")

        # Run multiple queries in the same session
        result1 = await session.run("What is Python?")
        print(f"Result 1: {result1.text[:100] if result1.text else 'No text'}...")

        result2 = await session.run("Name 3 Python web frameworks")
        print(f"Result 2: {result2.text[:100] if result2.text else 'No text'}...")

        # Get session summary
        print(f"\nSession summary: {session.get_summary()}")


async def example_safety_modes():
    """Example 5: Safety modes"""
    print("\n" + "=" * 60)
    print("Example 5: Safety Modes")
    print("=" * 60)

    config = load_config()

    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
    )

    tools = get_builtin_tools()
    memory = MemoryManager.create_simple()

    # Sandbox mode
    print("\n[Sandbox Mode]")
    sandbox_safety = SafetyManager(SafetyConfig(
        mode=SafetyMode.SANDBOX,
        allowed_dirs=["/tmp"],
        blocked_commands=["rm -rf", "sudo"],
    ))

    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=sandbox_safety,
        config=AgentConfig(max_loops=5),
    )

    print(f"Safety config: {sandbox_safety.get_config_summary()}")


async def example_structured_logging():
    """Example 6: Structured logging"""
    print("\n" + "=" * 60)
    print("Example 6: Structured Logging")
    print("=" * 60)

    # Configure logging
    logger = configure_logging(level=LogLevel.DEBUG, json_format=False)

    config = load_config()

    llm = LLMClient(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
    )

    tools = get_builtin_tools()
    memory = MemoryManager.create_simple()
    safety = SafetyManager(SafetyConfig(mode=SafetyMode.TRUST))

    agent = AgentLoop(
        llm_client=llm,
        tools=tools,
        memory=memory,
        safety=safety,
        logger=logger,
        config=AgentConfig(max_loops=5, verbose=True),
    )

    result = await agent.run("Say hello")
    print(f"\nResult: {result.text if result.text else 'No text'}")


async def main():
    """Run all examples"""
    print("\n" + "=" * 60)
    print("Tiny-Agent Examples")
    print("=" * 60)

    # Check configuration
    config = load_config(validate=False)
    print(f"\nModel: {config.llm.model}")
    print(f"Base URL: {config.llm.base_url}")
    print(f"API Key: {'*' * 8 if config.llm.api_key else 'NOT SET'}")

    if not config.llm.api_key:
        print("\nWarning: No API key configured. Set ANTHROPIC_API_KEY environment variable.")
        return

    try:
        # Run examples
        await example_basic()
        # await example_with_hooks()  # Uncomment to test hooks
        # await example_streaming()   # Uncomment to test streaming
        # await example_session()     # Uncomment to test sessions
        # await example_safety_modes()  # Uncomment to test safety
        # await example_structured_logging()  # Uncomment to test logging

        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())