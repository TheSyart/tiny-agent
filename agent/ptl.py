"""PTL (Prompt Too Long) recovery handler.

When the LLM API rejects a request because the prompt exceeds the context
window, this module truncates the oldest message groups and retries —
mirroring Claude Code's ``truncateHeadForPTLRetry`` strategy.
"""

from __future__ import annotations

import math
from typing import Optional


class PTLHandler:
    """Stateless helpers for detecting and recovering from PTL errors."""

    # Phrases the Anthropic API uses for prompt-too-long rejections.
    _PTL_PHRASES = (
        "prompt is too long",
        "maximum context length",
        "too many tokens",
        "exceeds the maximum",
    )

    @classmethod
    def is_ptl_error(cls, error: Exception) -> bool:
        """Return True if *error* looks like a prompt-too-long rejection."""
        msg = str(error).lower()
        return any(phrase in msg for phrase in cls._PTL_PHRASES)

    @staticmethod
    def truncate_for_retry(
        messages: list[dict],
        drop_ratio: float = 0.2,
    ) -> Optional[list[dict]]:
        """Drop the oldest message groups to shrink the prompt.

        A "message group" is a consecutive user + assistant pair.  The first
        message is preserved if it looks like a compression summary (role
        ``"user"`` with content starting with ``[``), because it carries
        essential context.

        Returns a shorter message list, or ``None`` if there is nothing left
        to drop (caller should propagate the error).
        """
        if len(messages) <= 2:
            return None  # too few to truncate

        # Detect whether the first message is a compression summary.
        preserve_head = 0
        if messages and messages[0].get("role") == "user":
            content = messages[0].get("content", "")
            if isinstance(content, str) and content.startswith("["):
                preserve_head = 1

        droppable = messages[preserve_head:]

        # Calculate how many messages to drop (at least 2 — one group).
        n_drop = max(2, math.ceil(len(droppable) * drop_ratio))
        # Round up to even number so we drop complete pairs.
        n_drop = n_drop + (n_drop % 2)

        if n_drop >= len(droppable):
            return None  # would drop everything

        remaining = messages[:preserve_head] + droppable[n_drop:]
        return remaining if remaining else None
