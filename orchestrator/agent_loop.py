"""
Agent loop — ana döngü: düşün → tool çağır → sonuç al → tekrar.

State machine (LangGraph deseni) ile yönetilir. 
Context compression (Hermes deseni) ile token tasarrufu.
Skill injection (Superpowers session-start hook) ile session bootstrap.
"""

from __future__ import annotations
from typing import Optional, Callable
import asyncio
import json

from core.logger import log
from core.event_bus import bus
from core.constants import MAX_TURNS, DEFAULT_PROVIDER, DEFAULT_MODEL
from orchestrator.reasoning import ReasoningEngine
from orchestrator.context import Context
from orchestrator.state_machine import (
    StateMachine, AgentContext, AgentState, create_default_machine,
)
from orchestrator.compressor import ContextCompressor
from skills.manager import skills

# P2-13: Checkpoint integration
from orchestrator.checkpoint import checkpoint_manager

# Extracted state handlers
from orchestrator.handlers import build_handlers


class AgentLoop:
    """
    Ana agent döngüsü. State machine ile:
        IDLE → THINKING → (TOOL_CALLING + RESULT → THINKING → DONE)
                        → (DIRECT_REPLY → DONE)
    """

    def __init__(self):
        self.reasoning = ReasoningEngine()
        self.context = Context()
        self.sm = create_default_machine()
        self.compressor = ContextCompressor()
        self.turn = 0
        self._skills_injected = False  # P0-05: sadece ilk turda skill injection
        self._session_titled = False  # Otomatik title
        self._temp_mode = False  # Gecici sohbet modu (kayit yok)


    async def process(self, user_input: str) -> str:
        """Process user input via state machine."""
        from soul.personality import soul
        from ui.status_bar import status as _status

        # ─── PROLOGUE (Çağrı Öncesi Hazırlık) ───
        # Sanitize input: clean surrogates and invalid characters
        import re
        if user_input:
            # Remove UTF-16 surrogates if any slipped through
            user_input = user_input.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
            # Remove control characters except newline and tab
            user_input = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', user_input)
            
        self.turn += 1
        _status.start_turn()
        self._streamed_this_turn = False  # Reset streaming flag for this turn
        # Self-reflection: track repeated tool errors
        if not hasattr(self, '_error_patterns'):
            self._error_patterns = {}  # tool_name -> [error_sig, count]
        
        # ─── Selamlama Tespiti (Python tarafinda, LLM cagrisi yok) ───
        _greeting_kelimeler = {"merhaba", "selam", "hey", "hi", "hello", "naber", "nasilsin", "nasılsın", "günaydın", "gunaydin", "iyi geceler", "kolay gelsin"}
        _user_lower = (user_input or "").lower().strip().rstrip(".!?,")
        # Sadece selamlama kelimelerinden olusuyorsa (en fazla 3 kelime)
        _words = set(_user_lower.split())
        if _words and _words.issubset(_greeting_kelimeler | {"talha", "dorina"}) and len(_words) <= 3:
            _status.set_status("idle")
            self.turn = max(0, self.turn - 1)
            _ad = ""
            for _w in _words:
                if _w.lower() not in _greeting_kelimeler and _w.lower() != "dorina":
                    _ad = _w
                    break
            _selam = "Merhaba" if "merhaba" in _user_lower else "Selam"
            _yanit = f"{_selam}{' ' + _ad.title() if _ad else ''}! Sana nasil yardimci olabilirim?"
            self.context.add_assistant_message(_yanit)
            return _yanit
        if self.turn > MAX_TURNS:
            _status.set_status("idle")
            return "Maximum turns reached. Use /new to reset."

        # P0-05: Otomatik session title — ilk mesajdan
        if self.turn == 1 and not self._session_titled:
            _title = (user_input or "").strip()[:60]
            if _title:
                from session.manager import manager
                try:
                    manager.rename(manager.current_id, _title)
                    self._session_titled = True
                except Exception:
                    pass

        # P0-05: Skill injection at session start
        if not self._skills_injected:
            self._active_skills = skills.get_applicable_skills(user_input)
            if self._active_skills:
                skill_sections = []
                for s in self._active_skills:
                    content = s['content']
                    if isinstance(content, dict):
                        content = content.get('content', '') or str(content)
                    # Skill icerigini kisitla: ilk 500 karakter yeterli
                    if len(content) > 500:
                        content = content[:500] + f"\n[...{len(content)-500} karakter daha, /skills {s['name']} ile tamami goruntulenebilir]"
                    skill_sections.append(f"## Skill: {s['name']} ({s['trigger']})\n{content}")
                self._cached_skills_text = "\n\n".join(skill_sections)
                self._enriched_system_prompt = f"{soul.system_prompt}\n\n---\n### Loaded Skills\n{self._cached_skills_text}"
                log.info(f"Skills injected: {[s['name'] for s in self._active_skills]}")
            else:
                self._cached_skills_text = ""
                self._enriched_system_prompt = soul.system_prompt
            self._skills_injected = True
        else:
            if getattr(self, '_cached_skills_text', ""):
                self._enriched_system_prompt = f"{soul.system_prompt}\n\n---\n### Loaded Skills\n{self._cached_skills_text}"
            else:
                self._enriched_system_prompt = soul.system_prompt

        # Context compression at 75% fill
        if self.compressor.should_compress(self.context.get_messages()):
            compressed = await self.compressor.compress(self.context.get_messages(), self._summarize)
            self.context.messages = compressed

        self.context.add_user_message(user_input)

        # Build state machine context and run
        ctx = AgentContext(
            state=AgentState.IDLE,
            user_input=user_input,
            turn=self.turn,
        )

        handlers = build_handlers(self)

        result = await self.sm.run(ctx, handlers)

        # Handle error state
        if ctx.state == AgentState.ERROR:
            return f"Hata: {ctx.error or 'Bilinmeyen hata'}"

        # Handle truncated case (still in THINKING)
        if result.startswith("Hata:"):
            return result

        return ctx.final_response or result

    def _update_status(self, response: dict):
        from ui.status_bar import status
        status.add_tokens(
            prompt_tokens=response.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=response.get("usage", {}).get("completion_tokens", 0),
            cost=response.get("cost", 0),
        )

    def _handle_tool_error(self, name: str, error: Exception, tool_call_id: str):
        """Handle tool execution error with self-reflection.
        
        Tracks repeated errors by pattern. After 3 consecutive same errors
        on the same tool, injects a strategy-change instruction into context.
        """
        from core.error_classifier import classify_api_error, sanitize_tool_error
        from core.error_db import log_tool_error
        from ui import display as _display
        from rich.markup import escape as _esc
        classified = classify_api_error(error)
        _safe_name = _esc(str(name))
        _safe_reason = _esc(str(classified.reason))
        _safe_error = _esc(str(error))
        log.error("Tool execution error [%s]: %s — %s", _safe_name, _safe_reason, _safe_error)
        _display.print_tool_error(_safe_name, _safe_reason + ": " + _safe_error)
        self.context.add_tool_result(name, sanitize_tool_error(str(error)), tool_call_id)
        log_tool_error(
            tool_name=name, message=str(error),
            context={"reason": classified.reason, "retryable": classified.retryable},
        )
        
        # Self-reflection: track error patterns
        if not hasattr(self, '_error_patterns'):
            self._error_patterns = {}
        sig = f"{name}:{classified.reason}"
        prev = self._error_patterns.get(sig, [sig, 0])
        prev[1] += 1
        self._error_patterns[sig] = prev
        
        # Hafıza Katmanı (Memory Layer) - check past learnings
        try:
            from evolution.self_check import get_relevant_learnings
            _past_lesson = get_relevant_learnings(str(error))
            if _past_lesson:
                self.context.add_user_message(f"[HAFIZA] Benzer bir hatayı geçmişte yaşadık. İşte önceki ders:\n{_past_lesson}")
                _display.print_info("Geçmişte benzer bir hata bulundu, hafıza uyandırıldı.")
        except Exception as _mem_e:
            log.error("Memory layer lookup failed during error handling: %s", _mem_e)
        
        # 3+ same errors on same tool → force strategy change
        if prev[1] >= 3:
            log.warning(f"Self-reflection: {sig} repeated {prev[1]}x — forcing strategy change")
            self.context.add_user_message(
                f"[SELF-REFLECTION] '{name}' aracı {prev[1]} kez aynı hatayı verdi: {classified.reason}. "
                f"Bu aracı tekrar kullanma. Farklı bir yaklaşım dene veya kullanıcıya durumu bildir."
            )
            self._error_patterns[sig][1] = 0  # Reset counter

    async def _summarize(self, messages_text: str) -> str:
        """Context compression için özetleme."""
        result = await self.reasoning.think(
            "You summarize conversations. Be concise.",
            [{"role": "user", "content": messages_text}],
        )
        return result.get("content", messages_text[:500])

    def reset(self):
        """Reset counters, new session."""
        from tools.executor import executor
        from ui.status_bar import status
        self.turn = 0
        self.context.clear()
        log.info(f"Context reset: {len(self.context.messages)} messages, {self.context.estimated_tokens} tokens")
        self.sm.reset_history()
        self.compressor.reset()
        executor.reset_count()
        status.reset()
        self._skills_injected = False  # P0-05: yeni session'da tekrar injection
        self._session_titled = False  # Yeni session'da yeni title
        self._temp_mode = False  # Temp modu kapat

    def _repair_message_sequence(self):
        """Ensure strict role alternation: assistant(tool_calls) -> tool -> tool -> ...
        
        If a non-tool message (like a user message injected by a tool) is found 
        while an assistant message is still waiting for its tool responses, 
        that non-tool message is pushed AFTER all the tool responses.
        """
        msgs = self.context.messages
        if not msgs:
            return

        reordered = []
        pending_non_tools = []
        active_tool_calls = set()

        for msg in msgs:
            role = msg.get("role", "")
            
            if role == "assistant" and msg.get("tool_calls"):
                # If we had any pending non-tools from a previous block, flush them
                reordered.extend(pending_non_tools)
                pending_non_tools = []
                
                reordered.append(msg)
                active_tool_calls = {tc.get("id", "") for tc in msg["tool_calls"]}
                
            elif role == "tool":
                tc_id = msg.get("tool_call_id", "")
                if tc_id in active_tool_calls:
                    reordered.append(msg)
                    active_tool_calls.discard(tc_id)
                else:
                    # Orphaned tool message, ignore or just append
                    pass
                    
                # If all tool calls for the current assistant are fulfilled, flush pending non-tools
                if not active_tool_calls and pending_non_tools:
                    reordered.extend(pending_non_tools)
                    pending_non_tools = []
                    
            else:
                # User or normal Assistant message
                if active_tool_calls:
                    # We are in the middle of fulfilling tool calls! Buffer it.
                    pending_non_tools.append(msg)
                else:
                    # Safe to append immediately
                    reordered.append(msg)

        # Flush any remaining pending messages at the end
        if pending_non_tools:
            reordered.extend(pending_non_tools)

        self.context.messages = reordered

    PLANNING_PATTERNS = [
        "önce", "hemen", "başlıyorum", "başlayalım",
        "let me", "i'll", "i will", "first", "let's",
        "şimdi", "bakalım", "kontrol", "analiz",
        "okuyup", "görelim", "araştır", "plan",
        "incele", "düzelt", "yapıyorum", "yapalım",
        "adım", "step", "adımlar", "steps",
        "öncelikle", "ilk olarak", "ilk adım",
        "devam", "continue", "proceed",
        "ardından", "sonra", "daha sonra",
        "önce şunu", "şu adımları", "aşağıdaki",
        "i'll start", "starting with", "begin by",
        "first,", "firstly", "secondly", "finally",
        "planlanan", "planlıyorum", "planım",
    ]

    FORCE_TOOL_PATTERNS = [
        "oku", "yaz", "çalıştır", "oluştur", "düzenle",
        "read", "write", "create", "run", "execute",
    ]

    @staticmethod
    def _clean_content(content: str) -> str:
        """Remove hallucinated XML tool call syntax from LLM text output."""
        import re as _re
        for pat in [
            r'<invoke(?:\s+[^>]*)?>.*?</invoke>',  # <invoke>, <invoke name="x">, <invoke name="x" extra="y">
            r'<tool_calls>.*?</tool_calls>',
            r'<function[^>]*>.*?</function>',  # <function=search>, <function name="x">, bare <function>
            r'\[tool_calls\].*?\[/tool_calls\]',
            r'<function_calls>.*?</function_calls>',
            r'<tool_call>.*?</tool_call>',
            r'<function_call>.*?</function_call>',
            r'<tool(?:\s+[^>]*)?>.*?</tool>',  # <tool name="x">, <tool name="x" extra="y">
            r'<action>.*?</action>',
            r'<parameter[^>]*>.*?</parameter>',  # stray parameter tags
        ]:
            content = _re.sub(pat, '', content, flags=_re.DOTALL | _re.IGNORECASE)
        content = _re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # collapse excess blank lines
        content = content.strip()
        # If only punctuation/symbols remain after cleanup, clear it
        if content and not _re.search(r'[a-zA-Z0-9\u0080-\uFFFF]', content):
            content = ""
        return content

    async def cleanup(self):
        """Cleanup resources: close DB, browsers, litellm, etc."""
        from session.manager import manager
        from ui.status_bar import status
        
        # Session bitisinde export + index
        if manager.current_id and self.context.get_messages():
            try:
                messages = self.context.get_messages()
                # Tool cagrilarini mesajlardan cikar
                tool_calls_data = []
                for m in messages:
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            fn = tc.get("function", {})
                            tool_calls_data.append({
                                "name": fn.get("name", "?"),
                                "args_preview": str(fn.get("arguments", ""))[:100],
                            })
                
                token_total = sum(len(str(m.get("content") or "")) for m in messages) // 4
                
                # Export
                from session.exporter import export_session
                export_session(
                    session_id=manager.current_id,
                    messages=messages,
                    summary=getattr(self, '_last_summary', ''),
                    title=getattr(self, '_last_title', ''),
                    model=DEFAULT_MODEL,
                    tool_calls_data=tool_calls_data,
                    token_total=token_total,
                )
                
                # Session indexing removed
            except Exception as e:
                log.error(f"Session export/index failed: {e}")
        
        if manager.db:
            manager.db.close()
        log.info("Session DB closed")
        status.reset()
        log.info("Agent reset")
        # Gracefully shut down litellm async workers
        try:
            import litellm
            await litellm.close_litellm_async_clients()
        except Exception as _lite_e:
            log.warning("litellm close error: %s", _lite_e)


loop = AgentLoop()


# State handlers moved to orchestrator/handlers/
# Registered via build_handlers() imported above

