"""Çalışma belleği - anlık konuşma bağlamı."""

from typing import Optional


class WorkingMemory:
    """Anlık konuşma belleği. Kullanıcı mesajlarını ve yanıtları tutar."""

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.messages: list[dict] = []

    def add(self, role: str, content: str, tool_name: Optional[str] = None):
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

    def clear(self):
        self.messages.clear()

    @property
    def count(self) -> int:
        return len(self.messages)
