"""LLM Client for Tiny-Agent

Uses ``anthropic.AsyncAnthropic`` so that calls do not block the event loop.
Exposes a regular ``chat()`` for single-shot responses and ``stream_chat()``
for token-level streaming. Upstream errors are mapped onto the project's
``LLMError`` hierarchy so callers do not have to import the anthropic SDK.
"""

import os
from typing import Any, AsyncIterator, Optional

import anthropic
from anthropic import AsyncAnthropic

from .exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    PromptTooLongError,
)
from .types import (
    ContentBlock,
    LLMResponse,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)


def _map_anthropic_error(err: Exception) -> LLMError:
    """Translate an anthropic SDK exception into our hierarchy."""
    if isinstance(err, anthropic.AuthenticationError):
        return LLMAuthenticationError(str(err))
    if isinstance(err, anthropic.RateLimitError):
        retry_after: Optional[int] = None
        # The SDK exposes the response; pull Retry-After if present.
        response = getattr(err, "response", None)
        if response is not None:
            header = getattr(response, "headers", {}) or {}
            raw = header.get("retry-after") or header.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(float(raw))
                except (TypeError, ValueError):
                    retry_after = None
        return LLMRateLimitError(str(err), retry_after=retry_after)
    if isinstance(err, anthropic.APIConnectionError):
        return LLMConnectionError(str(err))
    if isinstance(err, anthropic.APIStatusError):
        # Detect prompt-too-long (HTTP 400 with specific message)
        msg_lower = str(err).lower()
        if any(p in msg_lower for p in (
            "prompt is too long", "maximum context length",
            "too many tokens", "exceeds the maximum",
        )):
            return PromptTooLongError(str(err))
        return LLMResponseError(str(err))
    if isinstance(err, anthropic.APIError):
        return LLMError(str(err))
    return LLMError(str(err))


class LLMClient:
    """Async client for the Anthropic Messages API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        timeout: Optional[float] = 120.0,
    ):
        self.base_url = base_url or os.getenv("ANTHROPIC_BASE_URL")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("MODEL_ID", "claude-sonnet-4-20250514")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        if self.timeout is not None:
            client_kwargs["timeout"] = self.timeout

        self._client = AsyncAnthropic(**client_kwargs)

    def _build_params(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        system: Optional[Any],
        max_tokens: Optional[int],
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        """Build API request parameters.

        ``system`` can be a plain string or a ``list[dict]`` of cache-control
        blocks produced by :meth:`SystemPromptBuilder.build_cached`.
        """
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            params["tools"] = tools
        if system:
            params["system"] = system
        params.update(extra)
        return params

    @staticmethod
    def _parse_content(raw_content: list) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        for block in raw_content:
            btype = getattr(block, "type", None)
            if btype == "text":
                blocks.append(TextBlock(text=block.text))
            elif btype == "thinking":
                blocks.append(ThinkingBlock(thinking=block.thinking))
            elif btype == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=block.id,
                        name=block.name,
                        input=dict(block.input or {}),
                    )
                )
        return blocks

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Single-shot chat request."""
        params = self._build_params(messages, tools, system, max_tokens, kwargs)

        try:
            response = await self._client.messages.create(**params)
        except anthropic.APIError as e:
            raise _map_anthropic_error(e) from e
        except Exception as e:  # network / unexpected
            raise LLMError(f"Unexpected LLM error: {e}") from e

        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=self._parse_content(list(response.content)),
            stop_reason=response.stop_reason or "end_turn",
            model=getattr(response, "model", self.model),
            usage={
                "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
                "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
            },
            message_id=getattr(response, "id", ""),
        )

    async def stream_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream a chat response.

        Yields tuples of ``(event_type, data)``:

        - ``("text_delta", str)``           — incremental text
        - ``("thinking_delta", str)``       — incremental thinking (MiniMax)
        - ``("tool_use", ToolUseBlock)``    — a completed tool use block
        - ``("message", LLMResponse)``      — final aggregated response
        """
        params = self._build_params(messages, tools, system, max_tokens, kwargs)

        try:
            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None:
                            delta_type = getattr(delta, "type", None)
                            if delta_type == "text_delta":
                                yield ("text_delta", delta.text)
                            elif delta_type == "thinking_delta":
                                yield ("thinking_delta", delta.thinking)
                    elif etype == "content_block_stop":
                        block = getattr(event, "content_block", None)
                        if block is not None:
                            block_type = getattr(block, "type", None)
                            if block_type == "tool_use":
                                yield (
                                    "tool_use",
                                    ToolUseBlock(
                                        id=block.id,
                                        name=block.name,
                                        input=dict(block.input or {}),
                                    ),
                                )
                            elif block_type == "thinking":
                                yield (
                                    "thinking_block",
                                    ThinkingBlock(thinking=block.thinking),
                                )

                final = await stream.get_final_message()
        except anthropic.APIError as e:
            raise _map_anthropic_error(e) from e
        except Exception as e:
            raise LLMError(f"Unexpected LLM streaming error: {e}") from e

        usage = getattr(final, "usage", None)
        yield (
            "message",
            LLMResponse(
                content=self._parse_content(list(final.content)),
                stop_reason=final.stop_reason or "end_turn",
                model=getattr(final, "model", self.model),
                usage={
                    "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
                    "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
                },
                message_id=getattr(final, "id", ""),
            ),
        )

    async def aclose(self) -> None:
        """Close underlying HTTP client."""
        await self._client.close()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
