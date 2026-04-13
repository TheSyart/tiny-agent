"""Short-term memory - Conversation history management"""

from collections import deque
from typing import Dict, List, Optional, Any
import json


class ShortTermMemory:
    """
    Short-term memory for managing conversation history

    Keeps recent messages in a fixed-size buffer.
    """

    def __init__(self, max_messages: int = 100):
        """
        Initialize short-term memory

        Args:
            max_messages: Maximum number of messages to keep
        """
        self.max_messages = max_messages
        self._messages: deque = deque(maxlen=max_messages)

    def add(self, message: Dict) -> None:
        """Add a message to the history"""
        self._messages.append(message)

    def add_message(self, message: Any) -> None:
        """Add a Message object to the history"""
        if hasattr(message, 'to_api_format'):
            self._messages.append(message.to_api_format())
        else:
            self._messages.append(message)

    def get_messages(self) -> List[Dict]:
        """Get all messages in the history"""
        return list(self._messages)

    def get_context(self) -> List[Dict]:
        """Get messages for LLM context (alias for get_messages)"""
        return self.get_messages()

    def get_last_n(self, n: int) -> List[Dict]:
        """Get the last n messages"""
        messages = list(self._messages)
        return messages[-n:] if len(messages) >= n else messages

    def clear(self) -> None:
        """Clear all messages"""
        self._messages.clear()

    def pop(self) -> Optional[Dict]:
        """Remove and return the last message"""
        if self._messages:
            return self._messages.pop()
        return None

    def __len__(self) -> int:
        return len(self._messages)

    def __bool__(self) -> bool:
        return bool(self._messages)

    def save_to_file(self, path: str) -> None:
        """Save history to a JSON file"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(list(self._messages), f, indent=2, ensure_ascii=False)

    def load_from_file(self, path: str) -> None:
        """Load history from a JSON file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                messages = json.load(f)
            self._messages.clear()
            for msg in messages:
                self._messages.append(msg)
        except FileNotFoundError:
            pass