"""File state cache for tracking read files and detecting stale content."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileState:
    """Snapshot of a file at read time."""

    path: str
    mtime: float
    size: int


class FileStateCache:
    """Tracks which files have been read and detects post-read modifications.

    Used by ToolUseContext so that tools (e.g. file_edit) can warn the LLM
    when it tries to edit a file it hasn't read yet, or when the file changed
    on disk since it was last read.
    """

    def __init__(self) -> None:
        self._cache: dict[str, FileState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_read(self, path: str) -> FileState:
        """Record that *path* was just read.  Returns the captured state."""
        abs_path = os.path.abspath(path)
        try:
            stat = os.stat(abs_path)
            state = FileState(path=abs_path, mtime=stat.st_mtime, size=stat.st_size)
        except OSError:
            state = FileState(path=abs_path, mtime=0.0, size=0)
        self._cache[abs_path] = state
        return state

    def has_been_read(self, path: str) -> bool:
        """Return True if *path* has been read during this context."""
        return os.path.abspath(path) in self._cache

    def is_stale(self, path: str) -> bool:
        """Return True if *path* was modified on disk since the last read."""
        abs_path = os.path.abspath(path)
        state = self._cache.get(abs_path)
        if state is None:
            return False  # never read — not stale, just unknown
        try:
            current_mtime = os.stat(abs_path).st_mtime
        except OSError:
            return True  # file disappeared
        return current_mtime != state.mtime

    def get(self, path: str) -> Optional[FileState]:
        """Return the cached state for *path*, or None."""
        return self._cache.get(os.path.abspath(path))

    def clone(self) -> "FileStateCache":
        """Create an independent copy (for sub-agent isolation)."""
        new = FileStateCache()
        new._cache = dict(self._cache)
        return new

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, path: str) -> bool:
        return self.has_been_read(path)
