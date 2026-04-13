"""Core type definitions for Tiny-Agent"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, List, Union


@dataclass
class ContentBlock:
    """Base class for content blocks"""
    type: str = "text"


@dataclass
class TextBlock(ContentBlock):
    """Text content block"""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock(ContentBlock):
    """Tool use content block - represents a tool call from the LLM"""
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock(ContentBlock):
    """Tool result content block - represents the result of a tool execution"""
    type: str = "tool_result"
    tool_use_id: str = ""
    content: Union[str, List[Any]] = ""
    is_error: bool = False


@dataclass
class ThinkingBlock(ContentBlock):
    """Thinking content block - represents model reasoning (MiniMax specific)"""
    type: str = "thinking"
    thinking: str = ""


@dataclass
class Message:
    """A message in the conversation"""
    role: Literal["user", "assistant", "system"]
    content: Union[str, List[ContentBlock]]

    def to_api_format(self) -> dict:
        """Convert to API format for LLM"""
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}

        # Convert content blocks to API format
        blocks = []
        for block in self.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
            elif isinstance(block, ToolResultBlock):
                # Ensure content is JSON serializable
                def _serialize(obj):
                    if isinstance(obj, str):
                        return obj
                    if isinstance(obj, (int, float, bool, type(None))):
                        return obj
                    if isinstance(obj, dict):
                        return {k: _serialize(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [_serialize(v) for v in obj]
                    # Fallback: convert unknown types to string
                    return str(obj)

                serialized_content = _serialize(block.content)

                blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block.tool_use_id,
                    "content": serialized_content,
                    "is_error": block.is_error
                })
            elif isinstance(block, ThinkingBlock):
                blocks.append({
                    "type": "thinking",
                    "thinking": block.thinking
                })

        return {"role": self.role, "content": blocks}


@dataclass
class LLMResponse:
    """Response from LLM"""
    content: List[ContentBlock]
    stop_reason: str
    model: str = ""
    usage: dict = field(default_factory=dict)
    message_id: str = ""

    @property
    def tool_uses(self) -> List[ToolUseBlock]:
        """Get all tool use blocks from the response"""
        return [b for b in self.content if isinstance(b, ToolUseBlock)]

    @property
    def text(self) -> str:
        """Get the text content from the response"""
        text_blocks = [b for b in self.content if isinstance(b, TextBlock)]
        return "\n".join(b.text for b in text_blocks)

    def to_message(self) -> Message:
        """Convert to a Message object"""
        return Message(role="assistant", content=self.content)


@dataclass
class ToolResult:
    """Result of a tool execution"""
    tool_use_id: str
    content: Union[str, List[Any]]
    is_error: bool = False

    def to_block(self) -> ToolResultBlock:
        """Convert to ToolResultBlock"""
        return ToolResultBlock(
            tool_use_id=self.tool_use_id,
            content=self.content,
            is_error=self.is_error
        )