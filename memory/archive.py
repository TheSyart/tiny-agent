"""Archive Store - persistent long-term session archive.

Each archived session is one JSON file under
``data/memory/archives/YYYY-MM-DD/sess_<id>.json`` containing the full
conversation transcript, an LLM-generated summary, and basic metadata.

Search is keyword-based (substring on summary + message text). This is
intentionally simple so it works with zero extra dependencies — a vector
backend can be added later as a drop-in replacement.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SessionMeta:
    id: str
    created_at: str
    summary: str
    message_count: int
    tool_calls: List[str]
    token_count: int
    tags: List[str]
    file_path: str

    def to_dict(self) -> dict:
        return asdict(self)


class ArchiveStore:
    """JSON-file based session archive."""

    def __init__(self, archive_dir: str = "./data/memory/archives"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _new_session_id() -> str:
        return f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    @staticmethod
    def _extract_text(messages: List[dict]) -> str:
        """Flatten all message text for keyword search."""
        chunks: List[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        chunks.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        chunks.append(f"{block.get('name', '')} {block.get('input', '')}")
        return "\n".join(chunks)

    @staticmethod
    def _collect_tool_calls(messages: List[dict]) -> List[str]:
        names: List[str] = []
        seen = set()
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name and name not in seen:
                        seen.add(name)
                        names.append(name)
        return names

    # ------------------------------------------------------------------
    async def archive_session(
        self,
        messages: List[dict],
        summary: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Write one archived session to disk. Returns the session id."""
        sid = session_id or self._new_session_id()
        now = datetime.now()
        day_dir = self.archive_dir / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        meta = metadata or {}
        record = {
            "id": sid,
            "created_at": now.isoformat(timespec="seconds"),
            "summary": summary,
            "tags": meta.get("tags", []),
            "token_count": int(meta.get("token_count", 0)),
            "tool_calls": self._collect_tool_calls(messages),
            "message_count": len(messages),
            "messages": messages,
        }

        file_path = day_dir / f"{sid}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        return sid

    # ------------------------------------------------------------------
    def _iter_files(self):
        """Yield every archive file, newest first."""
        if not self.archive_dir.exists():
            return
        day_dirs = sorted(
            [p for p in self.archive_dir.iterdir() if p.is_dir()],
            reverse=True,
        )
        for day in day_dirs:
            for f in sorted(day.glob("*.json"), reverse=True):
                yield f

    def _load_meta(self, path: Path) -> Optional[SessionMeta]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return SessionMeta(
            id=data.get("id", path.stem),
            created_at=data.get("created_at", ""),
            summary=data.get("summary", ""),
            message_count=data.get("message_count", len(data.get("messages", []))),
            tool_calls=data.get("tool_calls", []),
            token_count=data.get("token_count", 0),
            tags=data.get("tags", []),
            file_path=str(path),
        )

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[dict]:
        results: List[dict] = []
        skipped = 0
        for path in self._iter_files():
            if skipped < offset:
                skipped += 1
                continue
            meta = self._load_meta(path)
            if meta is None:
                continue
            results.append(meta.to_dict())
            if len(results) >= limit:
                break
        return results

    async def load_session(self, session_id: str) -> Optional[dict]:
        for path in self._iter_files():
            if path.stem == session_id:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (OSError, json.JSONDecodeError):
                    return None
        return None

    async def search(self, query: str, limit: int = 10) -> List[dict]:
        """Case-insensitive substring search over summary + message text.

        Very simple scoring: summary matches weigh more than body matches.
        """
        if not query:
            return []
        q = query.lower().strip()
        tokens = [t for t in re.split(r"\s+", q) if t]
        if not tokens:
            return []

        scored: List[tuple[int, dict]] = []
        for path in self._iter_files():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            summary = (data.get("summary") or "").lower()
            body = self._extract_text(data.get("messages", [])).lower()

            score = 0
            for t in tokens:
                score += summary.count(t) * 3
                score += body.count(t)
            if score <= 0:
                continue

            scored.append(
                (
                    score,
                    {
                        "id": data.get("id", path.stem),
                        "created_at": data.get("created_at", ""),
                        "summary": data.get("summary", ""),
                        "message_count": data.get("message_count", 0),
                        "tool_calls": data.get("tool_calls", []),
                        "score": score,
                    },
                )
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]
