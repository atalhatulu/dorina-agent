"""BaseMemory — ortak bellek arayuzu (P2-02).

Her bellek turu bu sinifi miras alir ve asgari su ortak methodlari saglar:
    - add(key, content, metadata)  — veri ekle
    - get(key)                     — anahtarla getir
    - search(query, n_results)     — icerikte ara
    - delete(key)                  — anahtarla sil
    - clear()                      — tamamini temizle
    - count()                      — eleman sayisi

Her bellek kendine ozgu methodlarini korur (ornek: EpisodicMemory.save_session).
"""

from __future__ import annotations
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class MemoryProtocol(Protocol):
    """Structural typing protocol for memory systems."""

    def add(self, key: str, content: str, metadata: Optional[dict] = None) -> Any: ...
    def get(self, key: str) -> Any: ...
    def search(self, query: str, n_results: int = 5) -> list[dict]: ...
    def delete(self, key: str) -> bool: ...
    def clear(self) -> None: ...
    def count(self) -> int: ...


class BaseMemory:
    """Base class for all memory systems.

    Provides default docstrings and fallback implementations.
    Subclasses should override as needed.
    """

    memory_type: str = "abstract"

    def add(self, key: str, content: str, metadata: Optional[dict] = None):
        """Store a memory entry."""
        raise NotImplementedError

    def get(self, key: str):
        """Retrieve a memory entry by key."""
        raise NotImplementedError

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Search memory contents matching query."""
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        """Delete a memory entry by key."""
        raise NotImplementedError

    def clear(self):
        """Clear all memory contents."""
        raise NotImplementedError

    def count(self) -> int:
        """Number of entries in this memory."""
        raise NotImplementedError
