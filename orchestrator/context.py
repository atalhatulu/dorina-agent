"""Context management — message history, token budget."""

from core.constants import MAX_WORKING_MESSAGES
from core.tokenizer import count_tokens, count_messages_tokens

TOOL_RESULT_FULL_JSON = 800
TOOL_RESULT_PREVIEW = 4000
TOOL_RESULT_TRUNCATE = 1500

def _decide_result_policy(tool_name: str, result: str) -> tuple[str, int]:
    """(policy, limit). policy: full|preview|truncate"""
    if tool_name == "read_file":
        return "full", 0
        
    try:
        if result.startswith("{"):
            import json as _j
            parsed = _j.loads(result)
            if "error" not in parsed and len(result) <= TOOL_RESULT_FULL_JSON:
                return "full", 0
    except Exception:
        pass
        
    lower_res = result.lower()
    has_error = "error" in lower_res or "hata" in lower_res or "traceback" in lower_res
    
    if tool_name in ("web_search", "web_fetch", "knowledge"):
        return "preview", TOOL_RESULT_PREVIEW
        
    if tool_name == "terminal":
        if has_error:
            return "preview", TOOL_RESULT_PREVIEW
        return "truncate", TOOL_RESULT_TRUNCATE
        
    return "truncate", TOOL_RESULT_TRUNCATE


class Context:
    """Conversation context. Holds messages, manages token limits."""

    def __init__(self, model_name: str = ""):
        self.messages: list[dict] = []
        self.estimated_tokens = 0
        self._model_name = model_name

    def add_user_message(self, content: str):
        """Add a user message."""
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str):
        """Add an assistant message."""
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_name: str, result: str, tool_call_id: str = ""):
        """Add a tool result (with tool_call_id). Provenance format."""
        policy, limit = _decide_result_policy(tool_name, result)
        
        has_error_marker = False
        if result.startswith("{"):
            try:
                import json as _j
                parsed = _j.loads(result)
                if "error" in parsed:
                    has_error_marker = True
            except Exception:
                pass
        elif result.startswith("✗") or "error" in result[:50].lower():
            has_error_marker = True
            
        marker = "✗ " if has_error_marker else ""
        content = f"[{tool_name}] → {marker}{result}"
        
        if policy == "full":
            pass
        elif policy == "preview":
            if len(content) > limit:
                half = limit // 2
                preview = content[:half] + "\n...\n" + content[-half:]
                content = f"{preview}\n... (truncated, {len(result)} bytes total. use {tool_name} for full)"
        elif policy == "truncate":
            if len(content) > limit:
                preview = content[:limit]
                content = f"{preview}\n... (truncated, {len(result)} bytes total. use {tool_name} for full)"
        
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
        """Return all messages."""
        return self.messages

    def _trim(self):
        """Enforce max message count. Keep tool_result + tool_calls groups atomic.

        Split messages into atomic groups, then drop the oldest groups.
        An atomic group is never split — either the whole group is removed or none of it.
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
        """Clear the context."""
        self.messages.clear()
        self.estimated_tokens = 0

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def estimate_tokens(self) -> int:
        """Token count: tiktoken (if available) or char/4 fallback."""
        total = count_messages_tokens(self.messages, self._model_name)
        self.estimated_tokens = total
        return total
