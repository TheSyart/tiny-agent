"""
Agent Loop - Core execution loop for Tiny-Agent

This is a production-grade implementation of the agentic loop pattern with:
- Structured logging
- Hooks lifecycle
- Error handling
- Session management
- Streaming support
"""

import asyncio
from typing import Any, Optional, Callable, Awaitable, AsyncIterator, Union
from dataclasses import dataclass, field, fields
from enum import Enum

from .llm_client import LLMClient
from .types import (
    Message,
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    LLMResponse,
    ToolResult,
)
from .exceptions import (
    TinyAgentError,
    MaxIterationsError,
    AgentInterruptedError,
    ToolExecutionError,
    LLMError,
)
from .logger import AgentLogger, get_logger, LogContext
from .hooks import HookRegistry, HookContext, HookEvent, HookResult


class AgentState(Enum):
    """Agent state"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Configuration for Agent"""
    max_loops: int = 50
    max_tokens: int = 4096
    system_prompt: str = "You are a helpful AI assistant."
    verbose: bool = False
    stream: bool = True  # Enable streaming by default

    # Retry configuration
    max_retries: int = 3
    retry_delay: float = 1.0

    # Token budget (optional)
    max_budget_tokens: Optional[int] = None


@dataclass
class AgentMetrics:
    """Metrics collected during agent execution"""
    total_loops: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    errors: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "total_loops": self.total_loops,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "duration_seconds": (
                (self.end_time or 0) - (self.start_time or 0)
            ) if self.start_time else 0,
        }


class AgentLoop:
    """
    Production-grade Agent Loop implementation

    Features:
    - Structured logging with context
    - Hook-based lifecycle management
    - Comprehensive error handling
    - Streaming support
    - Metrics collection
    - Interrupt support

    Usage:
        agent = AgentLoop(llm_client, tools, memory, safety)

        # Simple run
        result = await agent.run("Hello!")

        # Streaming
        async for event in agent.run_stream("Hello!"):
            print(event)

        # With session
        async with AgentSession(agent) as session:
            result = await session.run("Hello!")
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: "ToolRegistry",
        memory: "MemoryManager",
        safety: "SafetyManager",
        config: Optional[AgentConfig] = None,
        hooks: Optional[HookRegistry] = None,
        logger: Optional[AgentLogger] = None,

        # Callbacks (deprecated - use hooks instead)
        on_tool_call: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_tool_result: Optional[Callable[[str, Any], Awaitable[None]]] = None,
        on_message: Optional[Callable[[Message], Awaitable[None]]] = None,
    ):
        self.llm = llm_client
        self.tools = tools
        self.memory = memory
        self.safety = safety
        self.config = config or AgentConfig()
        self.hooks = hooks or HookRegistry()
        self.logger = logger or get_logger()

        # Backward compatibility callbacks
        self._on_tool_call = on_tool_call
        self._on_tool_result = on_tool_result
        self._on_message = on_message

        # State
        self._state = AgentState.IDLE
        self._interrupted = asyncio.Event()
        self._metrics = AgentMetrics()

        # Session context
        self.session_id: Optional[str] = None
        self.agent_id: str = f"agent_{id(self)}"

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def metrics(self) -> AgentMetrics:
        return self._metrics

    def interrupt(self) -> None:
        """Request agent interruption (thread-safe via asyncio.Event)"""
        self._interrupted.set()
        self.logger.warning("Agent interrupt requested")

    def _check_interrupt(self) -> None:
        """Check if agent was interrupted"""
        if self._interrupted.is_set():
            self._interrupted.clear()
            raise AgentInterruptedError("Agent was interrupted")

    def _update_logger_context(self, loop_count: int = 0, tool_name: Optional[str] = None) -> None:
        """Update logger context"""
        self.logger.set_context(
            agent_id=self.agent_id,
            session_id=self.session_id,
            loop_count=loop_count,
            tool_name=tool_name
        )

    async def _iterate_loop(
        self, user_input: str
    ) -> AsyncIterator[tuple[str, Any]]:
        """Shared state machine for ``run`` and ``run_stream``.

        Emits the same event stream as ``run_stream``:

        - ``("text", str)``
        - ``("tool_call", dict)``
        - ``("tool_result", dict)``
        - ``("done", Message)``  — final assistant message (also on max-loops)

        Errors propagate by raising.
        """
        self._state = AgentState.RUNNING
        self._metrics.start_time = asyncio.get_event_loop().time()
        self._interrupted.clear()

        user_message = Message(role="user", content=user_input)
        # Persist the user message up front so partial progress is not lost
        # if the loop raises mid-flight. Both run() and run_stream() used to
        # differ here; unify on "save on entry".
        self.memory.add_message(user_message)

        await self._trigger_hook(HookEvent.AGENT_START, {"input": user_input})
        await self._trigger_hook(HookEvent.USER_MESSAGE, {"message": user_message})

        # Memory context already contains the user message we just added.
        messages = self.memory.get_context()

        final_message: Optional[Message] = None
        loop_count = 0

        try:
            while loop_count < self.config.max_loops:
                self._check_interrupt()

                loop_count += 1
                self._metrics.total_loops = loop_count
                self._update_logger_context(loop_count=loop_count)

                self.logger.loop_start(loop_count, self.config.max_loops)
                await self._trigger_hook(
                    HookEvent.LOOP_START, {"loop_count": loop_count}
                )
                yield ("step_start", {"step": loop_count})

                try:
                    response = await self._call_llm(messages)
                except LLMError as e:
                    self._metrics.errors += 1
                    self.logger.error(f"LLM error: {e}")
                    raise

                # Token accounting — consistent across both entry points.
                if response.usage:
                    self._metrics.input_tokens += response.usage.get("input_tokens", 0)
                    self._metrics.output_tokens += response.usage.get("output_tokens", 0)
                    self._metrics.total_tokens = (
                        self._metrics.input_tokens + self._metrics.output_tokens
                    )

                if (
                    self.config.max_budget_tokens
                    and self._metrics.total_tokens > self.config.max_budget_tokens
                ):
                    self.logger.warning("Token budget exceeded")
                    final_message = Message(
                        role="assistant",
                        content="Token budget exceeded.",
                    )
                    break

                # Emit assistant content as it arrives.
                for block in response.content:
                    if isinstance(block, TextBlock):
                        if block.text:
                            yield ("text", block.text)
                    elif isinstance(block, ThinkingBlock):
                        if block.thinking:
                            yield ("thinking", block.thinking)
                    elif isinstance(block, ToolUseBlock):
                        yield (
                            "tool_call",
                            {
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            },
                        )

                if response.stop_reason != "tool_use":
                    final_message = response.to_message()
                    break

                # Tool-use branch: execute, emit results, loop again.
                self.logger.info(f"Executing {len(response.tool_uses)} tool(s)")
                self._metrics.tool_calls += len(response.tool_uses)

                tool_results = await self._execute_tools(
                    response.tool_uses, loop_count
                )

                # Annotate error results with recovery hints so the LLM can
                # self-correct instead of repeating the same mistake.
                for tr in tool_results:
                    if tr.is_error and isinstance(tr.content, str):
                        tr.content = (
                            f"{tr.content}\n\n"
                            "[Hint: The tool call failed. Review the error, "
                            "fix the parameters, and retry — or try a different approach.]"
                        )

                for tr in tool_results:
                    yield (
                        "tool_result",
                        {
                            "tool_use_id": tr.tool_use_id,
                            "content": tr.content,
                            "is_error": tr.is_error,
                        },
                    )

                messages.append(response.to_message().to_api_format())
                # Convert tool results to API format (not dataclass objects)
                user_content = []
                for tr in tool_results:
                    # Ensure content is JSON serializable
                    content = tr.content
                    if isinstance(content, str):
                        serialized = content
                    elif isinstance(content, (dict, list)):
                        serialized = content
                    else:
                        serialized = str(content)

                    user_content.append({
                        "type": "tool_result",
                        "tool_use_id": tr.tool_use_id,
                        "content": serialized,
                        "is_error": tr.is_error,
                    })
                messages.append({"role": "user", "content": user_content})

                await self._trigger_hook(
                    HookEvent.LOOP_END,
                    {"loop_count": loop_count, "stop_reason": response.stop_reason},
                )

            if final_message is None:
                # Max loops reached with no terminal response.
                self.logger.warning(
                    f"Max iterations reached: {self.config.max_loops}"
                )
                final_message = Message(
                    role="assistant",
                    content=(
                        "I've reached the maximum number of iterations. "
                        "Please try a simpler request."
                    ),
                )

            # Persist final assistant message and fire hooks.
            self.memory.add_message(final_message)
            await self._trigger_hook(
                HookEvent.ASSISTANT_MESSAGE, {"message": final_message}
            )
            if self._on_message:
                await self._on_message(final_message)
            await self._trigger_hook(
                HookEvent.LOOP_END,
                {"loop_count": loop_count, "stop_reason": "end_turn"},
            )

            yield ("done", final_message)

        except AgentInterruptedError:
            self._state = AgentState.STOPPED
            raise
        except Exception as e:
            self._state = AgentState.ERROR
            self._metrics.errors += 1
            await self._trigger_hook(HookEvent.AGENT_ERROR, {"error": e})
            raise
        finally:
            self._metrics.end_time = asyncio.get_event_loop().time()
            if self._state != AgentState.STOPPED:
                self._state = AgentState.IDLE
            await self._trigger_hook(
                HookEvent.AGENT_STOP, self._metrics.to_dict()
            )
            self.logger.loop_end(self._metrics.total_loops, "completed")

    async def cleanup(self) -> None:
        """Release resources (LLM HTTP connections, etc.)."""
        if hasattr(self.llm, "aclose"):
            await self.llm.aclose()

    async def run(self, user_input: str) -> Message:
        """Run the agent loop and return the final assistant message."""
        final: Optional[Message] = None
        async for event_type, data in self._iterate_loop(user_input):
            if event_type == "done":
                final = data
        if final is None:
            raise TinyAgentError("Agent loop ended without producing a final message")
        return final

    async def run_stream(
        self, user_input: str
    ) -> AsyncIterator[tuple[str, Any]]:
        """Run the agent loop and stream events to the caller."""
        try:
            async for event in self._iterate_loop(user_input):
                yield event
        except Exception as e:
            yield ("error", e)
            raise

    async def _call_llm(self, messages: list, retry_count: int = 0) -> LLMResponse:
        """Call LLM with retry logic"""
        await self._trigger_hook(HookEvent.PRE_LLM_REQUEST, {
            "messages_count": len(messages),
            "tools_count": len(self.tools.get_schemas())
        })

        self.logger.llm_request(len(messages), len(self.tools.get_schemas()))

        try:
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools.get_schemas(),
                system=self.config.system_prompt,
                max_tokens=self.config.max_tokens,
            )

            await self._trigger_hook(HookEvent.POST_LLM_RESPONSE, {
                "stop_reason": response.stop_reason,
                "usage": response.usage
            })

            self.logger.llm_response(response.stop_reason, response.usage)

            return response

        except LLMError as e:
            if retry_count < self.config.max_retries:
                self.logger.warning(f"LLM error, retrying ({retry_count + 1}/{self.config.max_retries})")
                await asyncio.sleep(self.config.retry_delay * (retry_count + 1))
                return await self._call_llm(messages, retry_count + 1)
            raise

    async def _execute_tools(
        self,
        tool_uses: list[ToolUseBlock],
        loop_count: int
    ) -> list[ToolResult]:
        """Execute tool calls with safety checks and hooks"""
        results = []

        # Separate IO-intensive and CPU-intensive for parallel execution
        io_tools = []
        cpu_tools = []

        for tu in tool_uses:
            if self.tools.is_io_intensive(tu.name):
                io_tools.append(tu)
            else:
                cpu_tools.append(tu)

        # Execute IO-intensive tools in parallel
        if io_tools:
            io_tasks = [
                self._execute_single_tool(tu, loop_count)
                for tu in io_tools
            ]
            io_results = await asyncio.gather(*io_tasks, return_exceptions=True)

            for tu, result in zip(io_tools, io_results):
                if isinstance(result, Exception):
                    results.append(ToolResult(
                        tool_use_id=tu.id,
                        content=str(result),
                        is_error=True
                    ))
                else:
                    results.append(result)

        # Execute CPU-intensive tools sequentially
        for tu in cpu_tools:
            result = await self._execute_single_tool(tu, loop_count)
            results.append(result)

        return results

    async def _execute_single_tool(
        self,
        tool_use: ToolUseBlock,
        loop_count: int
    ) -> ToolResult:
        """Execute a single tool with full lifecycle management"""
        import time

        self._update_logger_context(loop_count=loop_count, tool_name=tool_use.name)

        # Pre-tool hook
        hook_ctx = HookContext(
            event=HookEvent.PRE_TOOL_USE,
            session_id=self.session_id,
            loop_count=loop_count,
            tool_name=tool_use.name,
            tool_input=tool_use.input
        )
        hook_result = await self._trigger_hook(HookEvent.PRE_TOOL_USE, hook_ctx)

        # Check if hook modified input or blocked execution
        if hook_result and not hook_result.continue_:
            return ToolResult(
                tool_use_id=tool_use.id,
                content=hook_result.error_message or "Blocked by hook",
                is_error=True
            )

        if hook_result and hook_result.modified_input:
            tool_use.input = hook_result.modified_input

        # Callback (deprecated)
        if self._on_tool_call:
            await self._on_tool_call(tool_use.name, tool_use.input)

        self.logger.tool_call(tool_use.name, tool_use.input)

        # Safety check
        permission = await self.safety.check(tool_use)

        if permission == "deny":
            self.logger.warning(f"Tool denied by safety: {tool_use.name}")
            return ToolResult(
                tool_use_id=tool_use.id,
                content="Permission denied by safety policy",
                is_error=True
            )

        if permission == "confirm":
            self.logger.info(f"Waiting for user confirmation: {tool_use.name}")
            confirmed = await self.safety.wait_confirmation(tool_use)
            if not confirmed:
                return ToolResult(
                    tool_use_id=tool_use.id,
                    content="User declined the operation",
                    is_error=True
                )

        # Execute tool
        start_time = time.time()
        try:
            output = await self.tools.execute(tool_use.name, tool_use.input)
            duration_ms = (time.time() - start_time) * 1000

            self.logger.tool_result(tool_use.name, True, duration_ms)

            result = ToolResult(
                tool_use_id=tool_use.id,
                content=output
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.tool_result(tool_use.name, False, duration_ms)

            result = ToolResult(
                tool_use_id=tool_use.id,
                content=str(e),
                is_error=True
            )

            # Trigger error hook
            await self._trigger_hook(HookEvent.TOOL_ERROR, {
                "tool_name": tool_use.name,
                "error": e
            })

        # Post-tool hook
        await self._trigger_hook(HookEvent.POST_TOOL_USE, {
            "tool_name": tool_use.name,
            "tool_result": result,
            "duration_ms": duration_ms
        })

        # Callback (deprecated)
        if self._on_tool_result:
            await self._on_tool_result(tool_use.name, result)

        return result

    async def _trigger_hook(
        self,
        event: HookEvent,
        context: Union[HookContext, dict]
    ) -> Optional[HookResult]:
        """Trigger a hook event.

        Accepts either a prebuilt ``HookContext`` or a free-form dict of
        event data. When given a dict, only keys that correspond to real
        ``HookContext`` fields are forwarded to ``__init__``; the rest are
        stashed on the context under an ``extra`` attribute so handlers can
        still reach them without triggering ``TypeError``.
        """
        if isinstance(context, dict):
            known = {f.name for f in fields(HookContext)}
            init_kwargs = {k: v for k, v in context.items() if k in known}
            extra = {k: v for k, v in context.items() if k not in known}
            ctx = HookContext(
                event=event,
                agent_id=self.agent_id,
                session_id=self.session_id,
                **init_kwargs,
            )
            if extra:
                setattr(ctx, "extra", extra)
        else:
            ctx = context
            ctx.event = event

        return await self.hooks.trigger(event, ctx)