"""Working memory — current conversation context."""

from typing import Any, Optional

from memory.base import BaseMemory


class WorkingMemory(BaseMemory):
    """Current conversation memory. Holds user messages and responses."""

    memory_type = "working"

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.messages: list[dict] = []
        super().__init__()

    # ── BaseMemory compatibility methods ────────────────────────

    def add(self, key: str, content: str, metadata: Optional[dict] = None) -> None:
        """BaseMemory compatible: (role=key, content=content, metadata=tool_name)."""
        tool_name = (metadata or {}).get("tool_name") if metadata else None
        self._add_msg(role=key, content=content, tool_name=tool_name)

    def get(self, key: str) -> Any:
        """Get the last message matching a role."""
        for msg in reversed(self.messages):
            if msg.get("role") == key:
                return msg.get("content", "")
        return None

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Search message content for text."""
        results = []
        for msg in self.messages:
            content = msg.get("content", "")
            if query.lower() in content.lower():
                results.append(msg)
                if len(results) >= n_results:
                    break
        return results

    def delete(self, key: str) -> bool:
        """Delete messages by role."""
        before = len(self.messages)
        self.messages = [m for m in self.messages if m.get("role") != key]
        return len(self.messages) < before

    def clear(self):
        self.messages.clear()

    def count(self) -> int:
        return len(self.messages)

    # ── Original WorkingMemory API ────────────────────────────

    def _add_msg(self, role: str, content: str, tool_name: Optional[str] = None):
        """Original add() logic."""
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
