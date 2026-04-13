"""Hooks system for Tiny-Agent lifecycle events"""

from typing import Callable, Any, Awaitable, Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class HookEvent(Enum):
    """Hook event types"""
    # Tool lifecycle
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    TOOL_ERROR = "tool_error"

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    AGENT_ERROR = "agent_error"

    # Loop lifecycle
    LOOP_START = "loop_start"
    LOOP_END = "loop_end"

    # Message lifecycle
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"

    # LLM lifecycle
    PRE_LLM_REQUEST = "pre_llm_request"
    POST_LLM_RESPONSE = "post_llm_response"

    # Memory lifecycle
    MEMORY_SAVE = "memory_save"
    MEMORY_LOAD = "memory_load"


@dataclass
class HookContext:
    """Context passed to hook handlers"""
    event: HookEvent
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    loop_count: int = 0

    # Event-specific data
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_result: Optional[Any] = None
    error: Optional[Exception] = None

    # Message data
    message: Optional[Any] = None

    # Control flags
    should_continue: bool = True
    modified_input: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "event": self.event.value,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "loop_count": self.loop_count,
            "tool_name": self.tool_name,
        }


@dataclass
class HookResult:
    """Result from hook handler"""
    continue_: bool = True  # Whether to continue execution
    modified_input: Optional[dict] = None
    modified_result: Optional[Any] = None
    error_message: Optional[str] = None
    additional_context: Optional[str] = None


HookHandler = Callable[[HookContext], Awaitable[Optional[HookResult]]]


@dataclass
class HookRegistration:
    """A registered hook"""
    event: HookEvent
    handler: HookHandler
    priority: int = 0  # Lower = earlier execution
    name: Optional[str] = None


class HookRegistry:
    """
    Registry for hooks

    Hooks are called in priority order (lower first).
    A hook can stop execution by returning HookResult(continue_=False)

    Usage:
        registry = HookRegistry()

        @registry.on(HookEvent.PRE_TOOL_USE, "bash")
        async def check_bash_command(ctx: HookContext) -> HookResult:
            if "rm -rf" in ctx.tool_input.get("command", ""):
                return HookResult(continue_=False, error_message="Dangerous command")
            return HookResult()
    """

    def __init__(self):
        self._hooks: Dict[HookEvent, List[HookRegistration]] = {
            event: [] for event in HookEvent
        }
        self._matchers: Dict[str, Callable[[HookContext], bool]] = {}

    def register(
        self,
        event: HookEvent,
        handler: HookHandler,
        priority: int = 0,
        name: Optional[str] = None,
        matcher: Optional[Callable[[HookContext], bool]] = None
    ) -> None:
        """Register a hook handler"""
        registration = HookRegistration(
            event=event,
            handler=handler,
            priority=priority,
            name=name
        )

        self._hooks[event].append(registration)
        self._hooks[event].sort(key=lambda r: r.priority)

        if matcher:
            self._matchers[name or str(id(handler))] = matcher

    def on(
        self,
        event: HookEvent,
        matcher: Optional[str] = None,
        priority: int = 0
    ) -> Callable[[HookHandler], HookHandler]:
        """
        Decorator to register a hook

        Usage:
            @registry.on(HookEvent.PRE_TOOL_USE, "bash")
            async def my_hook(ctx: HookContext) -> HookResult:
                ...
        """
        def decorator(handler: HookHandler) -> HookHandler:
            def match_fn(ctx: HookContext) -> bool:
                if matcher is None:
                    return True
                if event == HookEvent.PRE_TOOL_USE or event == HookEvent.POST_TOOL_USE:
                    return ctx.tool_name == matcher or matcher in (ctx.tool_name or "")
                return True

            self.register(event, handler, priority, matcher)
            self._matchers[matcher or str(id(handler))] = match_fn
            return handler

        return decorator

    async def trigger(
        self,
        event: HookEvent,
        context: HookContext
    ) -> HookResult:
        """
        Trigger all hooks for an event

        Returns the last HookResult, or a default one if no hooks
        """
        result = HookResult()
        context.event = event

        for registration in self._hooks[event]:
            # Check matcher
            matcher_name = registration.name
            if matcher_name and matcher_name in self._matchers:
                if not self._matchers[matcher_name](context):
                    continue

            try:
                hook_result = await registration.handler(context)

                if hook_result:
                    result = hook_result

                    # Stop if hook says not to continue
                    if not hook_result.continue_:
                        break

                    # Apply modifications
                    if hook_result.modified_input:
                        context.modified_input = hook_result.modified_input

            except Exception as e:
                # Log error but continue
                import logging
                logging.getLogger("tiny-agent").error(
                    f"Hook error: {registration.name} - {e}"
                )

        return result

    def unregister(self, name: str) -> bool:
        """Unregister hooks by name"""
        found = False
        for event in HookEvent:
            self._hooks[event] = [
                h for h in self._hooks[event]
                if h.name != name
            ]
        if name in self._matchers:
            del self._matchers[name]
            found = True
        return found

    def clear(self) -> None:
        """Clear all hooks"""
        for event in HookEvent:
            self._hooks[event] = []
        self._matchers.clear()


# Global hook registry
_global_registry: Optional[HookRegistry] = None


def get_hook_registry() -> HookRegistry:
    """Get or create global hook registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
    return _global_registry