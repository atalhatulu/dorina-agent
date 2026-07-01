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

# Extracted utilities (was spagetti inside this class)
from orchestrator.cleaner import clean_content
from orchestrator.repair import repair_message_sequence

# Extracted greeting detection + session auto-titling
from orchestrator.greeting import is_greeting
from orchestrator.titler import autotitle


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
        self._prompt_cache: str = ""
        self._prompt_cache_turn: int = -1


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
        if is_greeting(user_input):
            _status.set_status("idle")
            self.turn = max(0, self.turn - 1)
            _user_lower = (user_input or "").lower().strip().rstrip(".!?,")
            _words = set(_user_lower.split())
            _ad = ""
            for _w in _words:
                if _w.lower() not in {"merhaba", "selam", "hey", "hi", "hello", "naber", "nasilsin", "nasılsın", "günaydın", "gunaydin", "iyi geceler", "kolay gelsin", "ne haber", "dorina"}:
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
            from session.manager import manager
            _title = autotitle(user_input, session_id=manager.current_id)
            if _title:
                self._session_titled = True

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
                # Basit gorevlerde kisa prompt, karmasikta uzun
                # Speed modunda da kisa prompt kullan
                from core.mode_manager import modes
                _simple = {"merhaba", "selam", "hey", "naber", "nasilsin", "gunaydin", "kolay gelsin", "ne haber"}
                if modes.is_on('speed') or (user_input or "").lower().strip().rstrip(".!?,") in _simple or len((user_input or "").split()) <= 3:
                    self._enriched_system_prompt = soul.system_prompt_short
                else:
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

        # [OPT] Eski read_file sonuclarini buda (son turdakiler kalsin)
        if len(self.context.messages) > 4:
            for msg in self.context.messages[:-1]:
                if msg.get("role") == "tool" and msg.get("name") == "read_file" and len(str(msg.get("content", ""))) > 200:
                    msg["content"] = "[okundu]"

        # [OPT] System prompt cache: her 5 turda rebuild
        if self.turn - self._prompt_cache_turn >= 5 or not self._prompt_cache:
            self._prompt_cache = self._enriched_system_prompt
            self._prompt_cache_turn = self.turn
        self._enriched_system_prompt = self._prompt_cache

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
        from core.mode_manager import modes
        modes.reset()
        self.turn = 0
        self.context.clear()
        log.info(f"Context reset: {len(self.context.messages)} messages, {self.context.estimated_tokens} tokens")
        self.sm.reset_history()
        self.compressor.reset()
        executor.reset_count()
        status.reset()
        self._skills_injected = False  # P0-05: yeni session'da tekrar injection
        self._session_titled = False  # Yeni session'da yeni title
        # Sudo parolasini session sonunda temizle
        import soul.personality as _sp
        _sp.SUDO_PASSWORD = ""
        self._temp_mode = False  # Temp modu kapat

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
                
                # Export — runtime model kullan, static sabit degil
                from session.exporter import export_session
                from core.config import settings as _cfg
                export_session(
                    session_id=manager.current_id,
                    messages=messages,
                    summary=getattr(self, '_last_summary', ''),
                    title=getattr(self, '_last_title', ''),
                    model=_cfg.model.active_model or _cfg.model.default or DEFAULT_MODEL,
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

