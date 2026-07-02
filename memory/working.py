"""Çalışma belleği - anlık konuşma bağlamı."""

from typing import Any, Optional

from memory.base import BaseMemory


class WorkingMemory(BaseMemory):
    """Anlık konuşma belleği. Kullanıcı mesajlarını ve yanıtları tutar."""

    memory_type = "working"

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.messages: list[dict] = []
        super().__init__()

    # ── BaseMemory uyumluluk methodlari ────────────────────────

    def add(self, key: str, content: str, metadata: Optional[dict] = None) -> None:
        """BaseMemory uyumlu: (role=key, content=content, metadata=tool_name)."""
        tool_name = (metadata or {}).get("tool_name") if metadata else None
        self._add_msg(role=key, content=content, tool_name=tool_name)

    def get(self, key: str) -> Any:
        """Key ile eslesen son mesaji getir (role eslesmesi)."""
        for msg in reversed(self.messages):
            if msg.get("role") == key:
                return msg.get("content", "")
        return None

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Mesaj iceriginde metin ara."""
        results = []
        for msg in self.messages:
            content = msg.get("content", "")
            if query.lower() in content.lower():
                results.append(msg)
                if len(results) >= n_results:
                    break
        return results

    def delete(self, key: str) -> bool:
        """Role gore mesaj sil."""
        before = len(self.messages)
        self.messages = [m for m in self.messages if m.get("role") != key]
        return len(self.messages) < before

    def clear(self):
        self.messages.clear()

    def count(self) -> int:
        return len(self.messages)

    # ── Orijinal WorkingMemory API ────────────────────────────

    def _add_msg(self, role: str, content: str, tool_name: Optional[str] = None):
        """Orijinal add() mantigi."""
        entry = {"role": role, "content": content}
        if tool_name:
            entry["name"] = tool_name
        self.messages.append(entry)
        self._trim()

    def get_context(self) -> list[dict]:
        return self.messages

    def _trim(self):
        while len(self.messages) > self.max_messages:
            self.messages.pop(0)
