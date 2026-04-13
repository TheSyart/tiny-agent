"""Long-term memory implementations"""

import json
from pathlib import Path
from typing import Any, List, Optional
from datetime import datetime
from abc import ABC, abstractmethod


class MemoryBackend(ABC):
    """Abstract base class for memory backends"""

    @abstractmethod
    async def save(self, key: str, value: Any) -> None:
        """Save a memory"""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Any]:
        """Load a memory by key"""
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> List[Any]:
        """Search for relevant memories"""
        pass


class FilePersistence(MemoryBackend):
    """
    Simple file-based persistent storage

    Stores memories as JSON in a single file.
    """

    def __init__(self, storage_path: str = "./data/memory.json"):
        """
        Initialize file persistence

        Args:
            storage_path: Path to the storage file
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict = self._load()

    def _load(self) -> dict:
        """Load data from file"""
        if self.storage_path.exists():
            try:
                return json.loads(self.storage_path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}
        return {}

    def _save(self) -> None:
        """Save data to file"""
        self.storage_path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    async def save(self, key: str, value: Any) -> None:
        """Save a memory"""
        self._cache[key] = {
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        self._save()

    async def load(self, key: str) -> Optional[Any]:
        """Load a memory by key"""
        entry = self._cache.get(key)
        return entry["value"] if entry else None

    async def search(self, query: str, limit: int = 10) -> List[Any]:
        """Simple keyword search"""
        results = []
        query_lower = query.lower()

        for key, entry in self._cache.items():
            value_str = str(entry.get("value", "")).lower()

            if query_lower in key.lower() or query_lower in value_str:
                results.append(entry["value"])
                if len(results) >= limit:
                    break

        return results

    async def delete(self, key: str) -> bool:
        """Delete a memory by key"""
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    async def list_keys(self) -> List[str]:
        """List all keys"""
        return list(self._cache.keys())


class VectorStore(MemoryBackend):
    """
    Vector database storage using ChromaDB

    Provides semantic search capabilities.
    """

    def __init__(
        self,
        persist_directory: str = "./data/chroma",
        collection_name: str = "agent_memory"
    ):
        """
        Initialize vector store

        Args:
            persist_directory: Directory to persist the database
            collection_name: Name of the collection
        """
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "chromadb is required for VectorStore. "
                "Install it with: pip install chromadb"
            )

        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(collection_name)
        self._id_counter = 0

    async def save(self, key: str, value: Any, metadata: Optional[dict] = None) -> None:
        """Save to vector database"""
        self._id_counter += 1

        self.collection.add(
            documents=[str(value)],
            metadatas=[{"key": key, **(metadata or {})}],
            ids=[f"mem_{self._id_counter}"]
        )

    async def load(self, key: str) -> Optional[Any]:
        """Load by key (uses metadata filter)"""
        results = self.collection.get(
            where={"key": key}
        )

        if results["documents"]:
            return results["documents"][0]
        return None

    async def search(self, query: str, limit: int = 10) -> List[Any]:
        """Semantic search"""
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )

        return results["documents"][0] if results["documents"] else []

    async def delete(self, key: str) -> bool:
        """Delete by key"""
        results = self.collection.get(where={"key": key})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            return True
        return False

    async def count(self) -> int:
        """Count total documents"""
        return self.collection.count()