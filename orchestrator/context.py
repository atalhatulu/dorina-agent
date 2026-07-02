"""Bağlam yönetimi - mesaj geçmişi, token bütçesi."""

from core.constants import MAX_WORKING_MESSAGES
from core.tokenizer import count_tokens, count_messages_tokens


class Context:
    """Konuşma bağlamı. Mesajları tutar, token limitini yönetir."""

    def __init__(self, model_name: str = ""):
        self.messages: list[dict] = []
        self.estimated_tokens = 0
        self._model_name = model_name

    def add_user_message(self, content: str):
        """Kullanıcı mesajı ekle."""
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str):
        """Asistan mesajı ekle."""
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_name: str, result: str, tool_call_id: str = ""):
        """Tool sonucu ekle (tool_call_id ile). Provenans formatinda."""
        # read_file sonuclari truncate edilmez — LLM dosyayi tam gormeli
        if tool_name == "read_file":
            content = f"[{tool_name}] → {result}"
        elif result.startswith("{"):
            try:
                import json as _j
                parsed = _j.loads(result)
                if "error" in parsed:
                    content = f"[{tool_name}] → ✗ {parsed['error'][:200]}"
                else:
                    content = f"[{tool_name}] → {result}"
            except _j.JSONDecodeError:
                content = f"[{tool_name}] → {result}"
        elif result.startswith("✗") or "error" in result[:50].lower():
            content = f"[{tool_name}] → ✗ {result[:200]}"
        else:
            content = f"[{tool_name}] → {result}"

        # Buyuk tool sonuclarini kisalt (token tasarrufu) — read_file haric
        _MAX_TOOL_RESULT = 1500
        if tool_name != "read_file" and len(content) > _MAX_TOOL_RESULT:
            preview = content[:1500]
            content = f"{preview}\n... (truncated, {len(result)} bytes total. use read_file to see full content)"
        
        msg = {
            "role": "tool",
            "content": content,
            "name": tool_name,
        }
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
        self.messages.append(msg)
        self._trim()

    def get_messages(self) -> list[dict]:
        """Tüm mesajları döndür."""
        return self.messages

    def _trim(self):
        """Max mesaj sayısını aşma. Tool result + tool_calls gruplarını atomik tut.

        Mesajları önce atomik gruplara ayır, ardından en eski grupları sil.
        Bir atomik grup asla bölünmez — ya tamamı silinir ya da hiçbiri.
        """
        if len(self.messages) <= MAX_WORKING_MESSAGES + 2:
            return

        # Organize messages into atomic groups
        groups = []
        i = 0
        while i < len(self.messages):
            msg = self.messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Atomic group: assistant(tool_calls) + its tool result messages
                tc_ids = {tc.get("id", "") for tc in msg["tool_calls"]}
                group = [msg]
                i += 1
                while i < len(self.messages) and self.messages[i].get("role") == "tool":
                    if self.messages[i].get("tool_call_id", "") in tc_ids:
                        group.append(self.messages[i])
                        i += 1
                    else:
                        break
                groups.append(group)
            else:
                # Standalone message (user, assistant w/o tool_calls, etc.)
                groups.append([msg])
                i += 1

        # Remove oldest groups from front until target reached
        # Groups are atomic: never split a tool_calls+tools group
        target = len(self.messages) - MAX_WORKING_MESSAGES
        removed = 0
        keep = []
        for group in groups:
            if removed < target:
                # Remove entire group (may overshoot target slightly)
                removed += len(group)
            else:
                keep.extend(group)

        self.messages = keep

    def clear(self):
        """Bağlamı temizle."""
        self.messages.clear()
        self.estimated_tokens = 0

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def estimate_tokens(self) -> int:
        """Token sayısı: tiktoken (varsa) veya karakter/4 fallback."""
        total = count_messages_tokens(self.messages, self._model_name)
        self.estimated_tokens = total
        return total
