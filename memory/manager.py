"""Memory Manager - Unified memory management"""

from typing import Any, List, Optional
from pathlib import Path
import asyncio

from .short_term import ShortTermMemory
from .long_term import MemoryBackend, FilePersistence, VectorStore
from .archive import ArchiveStore
from .compressor import MemoryCompressor


class MemoryManager:
    """
    Unified memory management.

    Manages:
      - short-term (rolling conversation buffer)
      - long-term (key/value persistence backend)
      - archive (historical session JSON store, searchable)
      - compressor (optional LLM summarization of old messages)
    """

    def __init__(
        self,
        short_term: Optional[ShortTermMemory] = None,
        long_term: Optional[MemoryBackend] = None,
        archive: Optional[ArchiveStore] = None,
        compressor: Optional[MemoryCompressor] = None,
        auto_save: bool = True,
        history_file: Optional[str] = None,
    ):
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term
        self.archive = archive
        self.compressor = compressor
        self.auto_save = auto_save
        self.history_file = Path(history_file) if history_file else None
        self._storage_path: Optional[str] = None  # set by factory methods

        # Load history if file exists
        if self.history_file and self.history_file.exists():
            self.short_term.load_from_file(str(self.history_file))

        # Reentrancy guard: prevent compression loop from re-triggering.
        self._compressing = False

        # Cache for memory.md to avoid repeated file reads on every LLM call.
        self._important_cache: Optional[dict] = None
        self._important_mtime: float = 0.0

    # ------------------------------------------------------------------
    @classmethod
    def create_simple(
        cls,
        max_messages: int = 100,
        storage_path: str = "./data/memory",
        history_file: Optional[str] = None,
        compressor: Optional[MemoryCompressor] = None,
        archive_enabled: bool = True,
    ) -> "MemoryManager":
        """Create a simple memory manager with file persistence."""
        archive = (
            ArchiveStore(archive_dir=f"{storage_path}/archives") if archive_enabled else None
        )
        mgr = cls(
            short_term=ShortTermMemory(max_messages=max_messages),
            long_term=FilePersistence(storage_path=f"{storage_path}/long_term.json"),
            archive=archive,
            compressor=compressor,
            history_file=history_file or f"{storage_path}/history.json",
        )
        mgr._storage_path = storage_path
        return mgr

    @classmethod
    def create_with_vector(
        cls,
        max_messages: int = 100,
        persist_directory: str = "./data/chroma",
        history_file: Optional[str] = None,
        compressor: Optional[MemoryCompressor] = None,
        archive_dir: str = "./data/memory/archives",
        archive_enabled: bool = True,
    ) -> "MemoryManager":
        """Create a memory manager with vector store."""
        archive = ArchiveStore(archive_dir=archive_dir) if archive_enabled else None
        return cls(
            short_term=ShortTermMemory(max_messages=max_messages),
            long_term=VectorStore(persist_directory=persist_directory),
            archive=archive,
            compressor=compressor,
            history_file=history_file,
        )

    # ------------------------------------------------------------------
    def add_message(self, message: Any) -> None:
        """Add a message to short-term memory.

        If a compressor is attached and the threshold is reached, schedule
        an async compression pass (best-effort, does not block the caller).
        """
        self.short_term.add_message(message)
        self._save_history()

        if self.compressor and not self._compressing:
            try:
                msgs = self.short_term.get_messages()
                if self.compressor.should_compress(msgs):
                    # Fire-and-forget inside existing event loop.
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._compress_inline())
                    except RuntimeError:
                        # No running loop (sync context) — skip; UI or next
                        # async tick will trigger compression instead.
                        pass
            except Exception:
                pass

    def get_context(self) -> List[dict]:
        """Get conversation context for LLM, prepending memory.md if present."""
        messages = self.short_term.get_context()
        important = self._load_important_memories()
        if important:
            return [important] + messages
        return messages

    def _load_important_memories(self) -> Optional[dict]:
        """Load memory.md and return as a synthetic user message, or None.

        Uses mtime-based caching so we only re-read the file when it changes.
        """
        if not self._storage_path:
            return None
        path = Path(self._storage_path) / "memory.md"
        if not path.exists():
            self._important_cache = None
            return None
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return self._important_cache
        if mtime == self._important_mtime and self._important_cache is not None:
            return self._important_cache
        content = path.read_text(encoding="utf-8").strip()
        self._important_mtime = mtime
        if not content:
            self._important_cache = None
            return None
        self._important_cache = {
            "role": "user",
            "content": f"[重要记忆 — 每次对话自动加载]\n{content}",
        }
        return self._important_cache

    async def remember(self, key: str, value: Any) -> None:
        if self.long_term:
            await self.long_term.save(key, value)

    async def recall(self, key: str) -> Optional[Any]:
        if self.long_term:
            return await self.long_term.load(key)
        return None

    async def search(self, query: str, limit: int = 10) -> List[Any]:
        if self.long_term:
            return await self.long_term.search(query, limit)
        return []

    # ------------------------------------------------------------------
    async def recall_history(self, query: str, limit: int = 5) -> List[dict]:
        """Search archived sessions for prior conversations.

        Used by the ``memory_recall`` tool so the agent can answer
        questions referencing past sessions.
        """
        if not self.archive:
            return []
        return await self.archive.search(query, limit)

    async def load_archived_session(self, session_id: str) -> Optional[dict]:
        if not self.archive:
            return None
        return await self.archive.load_session(session_id)

    async def list_archived_sessions(self, limit: int = 50, offset: int = 0) -> List[dict]:
        if not self.archive:
            return []
        return await self.archive.list_sessions(limit, offset)

    # ------------------------------------------------------------------
    async def _compress_inline(self) -> int:
        """Replace old messages with a single LLM-generated summary.

        Returns the number of original messages that were collapsed.
        """
        if self._compressing or not self.compressor:
            return 0
        self._compressing = True
        try:
            messages = self.short_term.get_messages()
            summary_msg = await self.compressor.compress(messages)
            if not summary_msg or "__error__" in summary_msg:
                return 0

            keep_recent = self.compressor.keep_recent
            old_count = max(0, len(messages) - keep_recent)
            if old_count <= 0:
                return 0

            recent = messages[-keep_recent:] if keep_recent > 0 else []
            # Rebuild short-term buffer: [summary] + recent
            self.short_term.clear()
            self.short_term.add(summary_msg)
            for m in recent:
                self.short_term.add(m)
            self._save_history()
            return old_count
        finally:
            self._compressing = False

    async def force_compress(self) -> int:
        """Manually trigger compression (UI button)."""
        if not self.compressor:
            return 0
        return await self._compress_inline()

    # ------------------------------------------------------------------
    async def archive_current_session(
        self,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None,
        clear_after: bool = True,
    ) -> Optional[str]:
        """Archive current short-term buffer to disk.

        If ``summary`` is not provided and a compressor is available, generate
        one. Optionally clear short-term after archiving.
        """
        if not self.archive:
            return None

        messages = self.short_term.get_messages()
        if not messages:
            return None

        if summary is None and self.compressor:
            summary_msg = await self.compressor.compress(messages + [{"role": "user", "content": "<end of session>"}])
            if summary_msg and "__error__" not in summary_msg:
                text = summary_msg.get("content", "")
                # Strip the "[历史会话摘要 ...]" prefix line if present.
                if isinstance(text, str):
                    first_nl = text.find("\n")
                    summary = text[first_nl + 1 :] if first_nl >= 0 else text

        session_id = await self.archive.archive_session(
            messages=messages,
            summary=summary or "(no summary)",
            metadata=metadata or {},
        )

        # Only clear after archive succeeds — prevents data loss if archive
        # raises an exception mid-write.
        if clear_after and session_id:
            self.short_term.clear()
            self._save_history()

        return session_id

    # ------------------------------------------------------------------
    def clear_short_term(self) -> None:
        """Clear short-term memory"""
        self.short_term.clear()
        self._save_history()

    def _save_history(self) -> None:
        """Save history to file if auto_save is enabled"""
        if self.auto_save and self.history_file:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.short_term.save_to_file(str(self.history_file))
