"""Memory Compressor - Summarize old messages via LLM.

When short-term memory grows past a threshold, compress the older portion
into a single structured summary message so that the rolling window keeps
useful context without the raw token cost of full history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional


class MemoryCompressor:
    """Summarizes old conversation messages into one compact message."""

    def __init__(
        self,
        llm_client: Any,
        trigger_threshold: int = 60,
        keep_recent: int = 20,
        target_summary_tokens: int = 500,
        prompt_path: Optional[str] = None,
        trigger_ratio: float = 0.70,
        max_context_tokens: int = 4096,
    ):
        self.llm_client = llm_client
        self.trigger_threshold = trigger_threshold
        self.keep_recent = keep_recent
        self.target_summary_tokens = target_summary_tokens
        self._prompt_template: Optional[str] = None
        self._prompt_path = prompt_path or str(
            Path(__file__).parent.parent / "prompts" / "compress.md"
        )
        self.trigger_ratio = trigger_ratio
        self.max_context_tokens = max_context_tokens

    # ------------------------------------------------------------------
    def _estimate_tokens(self, messages: List[dict]) -> int:
        """Rough token estimate: Chinese/English mix ≈ 3 chars per token."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += max(len(content) // 3, 1)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text") or block.get("content") or ""
                        if isinstance(text, str):
                            total += max(len(text) // 3, 1)
        return total

    def should_compress(self, messages: List[dict]) -> bool:
        estimated = self._estimate_tokens(messages)
        threshold_tokens = int(self.max_context_tokens * self.trigger_ratio)
        return estimated >= threshold_tokens

    def _load_prompt(self) -> str:
        if self._prompt_template is None:
            try:
                self._prompt_template = Path(self._prompt_path).read_text(encoding="utf-8")
            except FileNotFoundError:
                self._prompt_template = (
                    "Summarize the following conversation into four sections: "
                    "用户意图 / 关键结论 / 涉及工具调用 / 未完成事项. "
                    "Target length: {target_tokens} tokens."
                )
        return self._prompt_template

    def _render_messages(self, messages: List[dict]) -> str:
        """Flatten message dicts into a plain-text transcript for the summarizer."""
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str):
                lines.append(f"[{role}] {content}")
                continue
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        lines.append(f"[{role}] {block}")
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        lines.append(f"[{role}] {block.get('text', '')}")
                    elif btype == "tool_use":
                        name = block.get("name", "?")
                        lines.append(f"[{role}/tool_use] {name}({block.get('input', {})})")
                    elif btype == "tool_result":
                        body = block.get("content", "")
                        if isinstance(body, list):
                            body = " ".join(
                                b.get("text", "") if isinstance(b, dict) else str(b)
                                for b in body
                            )
                        lines.append(f"[{role}/tool_result] {body}")
                    elif btype == "thinking":
                        # Drop thinking blocks from summary input.
                        continue
                    else:
                        lines.append(f"[{role}/{btype}] {block}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    async def compress(self, messages: List[dict]) -> Optional[dict]:
        """Summarize messages[:-keep_recent] into a single synthetic message.

        Returns the synthetic summary message (role="user" with marker prefix)
        or None if there's nothing to compress.
        """
        if len(messages) <= self.keep_recent:
            return None

        to_compress = messages[: len(messages) - self.keep_recent]
        if not to_compress:
            return None

        transcript = self._render_messages(to_compress)
        system_prompt = self._load_prompt().format(
            target_tokens=self.target_summary_tokens
        )

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": transcript}],
                system=system_prompt,
                max_tokens=self.target_summary_tokens * 2,
            )
        except Exception as e:
            # Compression is best-effort; on failure, leave memory alone.
            return {"__error__": str(e)}

        summary_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                summary_text += block.text

        if not summary_text.strip():
            return None

        return {
            "role": "user",
            "content": f"[历史会话摘要 · 已压缩 {len(to_compress)} 条]\n{summary_text.strip()}",
        }
