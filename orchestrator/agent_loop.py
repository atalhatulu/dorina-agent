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

    async def process_old(self, user_input: str) -> str:
        """[DEPRECATED] Old process logic — kept for reference during migration.
        Process user input — persist until task is done."""
        from ui.status_bar import status
        from soul.personality import soul
        from ui import display
        from tools.registry import registry
        from tools.executor import executor

        self.turn += 1
        status.start_turn()

        if self.turn > MAX_TURNS:
            return "Maximum turns reached. Use /new to reset."

        # ── P0-05: Skill injection at session start (sadece ilk tur) ──
        if not self._skills_injected:
            enriched_prompt = skills.inject_skills_to_prompt(
                session_context=user_input,
                system_prompt=soul.system_prompt,
            )
            if enriched_prompt != soul.system_prompt:
                log.info("Skills injected into system prompt at session start")
            self._skills_injected = True
            self._enriched_system_prompt = enriched_prompt
        else:
            self._enriched_system_prompt = getattr(self, '_enriched_system_prompt', soul.system_prompt)

        # Use enriched system prompt if available
        effective_system_prompt = getattr(self, '_enriched_system_prompt', soul.system_prompt)

        self.context.add_user_message(user_input)

        # Context compression at 75% fill
        if self.compressor.should_compress(self.context.get_messages()):
            compressed = await self.compressor.compress(self.context.get_messages(), self._summarize)
            self.context.messages = compressed

        # Repair message role alternation before sending to LLM
        self._repair_message_sequence()

        # ─── PERSISTENT TASK LOOP ──────────────────────────────────
        total_iterations = 0
        MAX_ITERATIONS = 15
        planning_warnings = 0

        while total_iterations < MAX_ITERATIONS:
            total_iterations += 1

            # THINK: ask LLM what to do next
            ctx = self.context.get_messages()
            # Debug: check for invalid messages before sending
            for i, m in enumerate(ctx):
                if m.get("role") == "assistant" and not m.get("content") and not m.get("tool_calls"):
                    log.warning(f"FIXING invalid assistant msg at idx {i}")
                    ctx[i] = {"role": "assistant", "content": "(continuing...)"}
            try:
                from tools.selector import selector as _sel
                _schemas = await _sel.schemas_for_context(user_input, top_k=15)
                response = await self.reasoning.think(
                    effective_system_prompt,
                    self.context.get_messages(),
                    _schemas,
                )
            except Exception as e:
                from core.error_classifier import classify_api_error, format_user_error
                from core.error_db import log_llm_error
                classified = classify_api_error(e, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
                user_msg = format_user_error(e, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
                log.error(f"LLM error: {classified.reason} — {e}")
                log_llm_error(str(e), category=classified.reason,
                              provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
                display.print_assistant(user_msg)
                return user_msg
            self._update_status(response)
            tool_calls = response.get("tool_calls", [])
            content = response.get("content", "")
            finish_reason = response.get("finish_reason", "stop")

            # Handle truncated response (token limit reached)
            if finish_reason == "length":
                log.warning("LLM response truncated (finish_reason=length), sending continuation prompt")
                self.context.add_assistant_message(content or "(devam ediyor...)")
                # If there were tool calls in progress, let the normal flow handle them
                if not tool_calls:
                    self.context.add_user_message("Devam et, cevabın kesildi. Kaldığın yerden devam et.")
                    continue

            # Clean up raw tool call syntax from content (model sometimes hallucinates XML tool calls in text)
            if content:
                content = self._clean_content(content)

            if not tool_calls:
                # Check if LLM is just planning/talking without doing
                if content and self._is_planning_only(content):
                    planning_warnings += 1
                    if planning_warnings >= 3:
                        # After 3 warnings, force plan_and_execute
                        from orchestrator.planner import planner

                        force_msg = (
                            "SADECE KONUSMA. plan_and_execute tool'unu cagirarak \"{}\" "
                            "gorevini alt-gorevlere bol ve calistir. "
                            "Kendin plan yapma, plan_and_execute'u kullan.".format(user_input)
                        )
                        self.context.messages.append({"role": "user", "content": force_msg})
                    elif planning_warnings >= 2:
                        # Second time: more direct
                        self.context.messages.append({
                            "role": "user",
                            "content": "Tool cagirmadan devam etme. Ilk adimi yap: dosyalari terminal ile oku veya direkt write_file kullan."
                        })
                    else:
                        # First time: gentle reminder
                        self.context.messages.append({
                            "role": "user",
                            "content": (
                                "TOOL KULLAN: Sadece plan yapip konusmak yeterli degil. "
                                "Hemen aksiyona gec. dosya okuyacaksan read_file cagir, "
                                "terminal komutu calistiracaksan terminal cagir."
                            )
                        })
                    continue
                # Task complete — clean up tool-related messages
                cleaned = []
                for m in self.context.get_messages():
                    role = m.get("role", "")
                    if role == "tool":
                        continue
                    if role == "assistant" and m.get("tool_calls"):
                        continue
                    cleaned.append(m)
                if content:
                    self.context.messages = cleaned
                    self.context.add_assistant_message(content)
                    return content
                # No content from LLM — keep full context for fallback synthesis below
                # (so the LLM can see tool results and generate a proper summary)
                break

            # EXECUTE tools
            assistant_msg = {
                "role": "assistant",
                "content": None if tool_calls else (content or ""),
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{tc['function']['name']}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls
                ],
            }
            self.context.messages.append(assistant_msg)

            # Parallel execution for read-only tools, sequential for write tools
            READ_TOOLS = frozenset({"read_file", "search_files", "web_search", "web_fetch", "browser_snapshot", "gif_search"})
            read_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") in READ_TOOLS]
            write_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") not in READ_TOOLS]

            async def _run_read_tool(tc):
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "{}")
                tool_call_id = tc.get("id", f"call_{name}")
                status.add_tool_call()
                display.print_tool_start(name, json.loads(args) if isinstance(args, str) else args)
                try:
                    result = await asyncio.to_thread(executor.execute, name, args)
                    self.context.add_tool_result(name, result, tool_call_id)
                    if "error" in result[:20].lower():
                        display.print_tool_error(name, result)
                    else:
                        display.print_tool_done(name, result)
                except Exception as e:
                    self._handle_tool_error(name, e, tool_call_id)

            def _run_write_tool(tc):
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "{}")
                tool_call_id = tc.get("id", f"call_{name}")
                status.add_tool_call()
                display.print_tool_start(name, json.loads(args) if isinstance(args, str) else args)
                try:
                    result = executor.execute(name, args)
                    self.context.add_tool_result(name, result, tool_call_id)
                    if "error" in result[:20].lower():
                        display.print_tool_error(name, result)
                    else:
                        display.print_tool_done(name, result)
                except Exception as e:
                    self._handle_tool_error(name, e, tool_call_id)

            # Run read tools in parallel
            if read_calls:
                await asyncio.gather(*[_run_read_tool(tc) for tc in read_calls])
            # Run write tools sequentially
            for tc in write_calls:
                _run_write_tool(tc)

            # ── P2-13: Auto-checkpoint after tool execution ──
            checkpoint_manager.update_turn(total_iterations)
            if checkpoint_manager.should_checkpoint:
                cp_state_data = self.context.get_messages() if hasattr(self.context, 'get_messages') else []
                await checkpoint_manager.save(
                    {
                        "turn": total_iterations,
                        "state": "thinking",
                        "messages": cp_state_data,
                        "metadata": {},
                        "sm_history": [],
                    },
                    cp_type="auto",
                )

        # Fallback: synthesize final answer from tool results
        from soul.personality import soul
        final = await self.reasoning.think(
            effective_system_prompt,
            self.context.get_messages(),
            [],
        )
        content = final.get("content", "")
        if content:
            # Also clean any hallucinated XML in the fallback response
            content = self._clean_content(content)
            self.context.add_assistant_message(content)
            return content
        return "Task completed. Use /help for available commands."

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
            _status.set_status("hazir")
            self.turn = max(0, self.turn - 1)  # Sayma bu turu
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
            return "Maximum turns reached. Use /new to reset."

        # P0-05: Skill injection at session start
        if not self._skills_injected:
            enriched = skills.inject_skills_to_prompt(
                session_context=user_input,
                system_prompt=soul.system_prompt,
            )
            if enriched != soul.system_prompt:
                log.info("Skills injected into system prompt at session start")
            self._skills_injected = True
            self._enriched_system_prompt = enriched
        else:
            self._enriched_system_prompt = getattr(self, '_enriched_system_prompt', soul.system_prompt)

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

        handlers = {
            "idle": _handle_idle,
            "thinking": _handle_thinking,
            "tool": _handle_tool_calling,
            "result": _handle_waiting_result,
            "synthesize": _handle_synthesize,
            "reply": _handle_direct_reply,
            "error": _handle_error,
            "done": _handle_done,
            "fallback": _handle_fallback,
        }

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
        except Exception:
            pass
        
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
        self.sm.reset_history()
        self.compressor.reset()
        executor.reset_count()
        status.reset()
        self._skills_injected = False  # P0-05: yeni session'da tekrar injection

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

    def _is_planning_only(self, content: str) -> bool:
        """Check if content is just planning/talking without action."""
        lower = content.lower()
        # Very short responses could be valid (e.g. "Dosya bulunamadi.")
        # Only flag if under 80 chars AND contains planning indicators
        if len(content) < 80:
            plan_count = sum(1 for p in self.PLANNING_PATTERNS if p in lower)
            return plan_count >= 1
        # Count planning indicators
        plan_count = sum(1 for p in self.PLANNING_PATTERNS if p in lower)
        # Long analysis text without tool calls is planning
        if plan_count >= 2:
            return True
        # Also catch cases where model talks about reading/writing without doing it
        if len(content) > 200:
            force_count = sum(1 for p in self.FORCE_TOOL_PATTERNS if p in lower)
            if force_count >= 2 and plan_count >= 1:
                return True
        return False

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
                
                # Index
                from knowledge.session_indexer import index_session
                index_session(
                    session_id=manager.current_id,
                    messages=messages,
                    summary=getattr(self, '_last_summary', ''),
                    tool_calls_data=tool_calls_data,
                )
            except Exception as e:
                log.debug(f"Session export/index skipped: {e}")
        
        if manager.db:
            manager.db.close()
        log.info("Session DB closed")
        status.reset()
        log.info("Agent reset")
        # Gracefully shut down litellm async workers
        try:
            import litellm
            await litellm.close_litellm_async_clients()
        except Exception:
            pass


loop = AgentLoop()


# ─── State Machine Handlers ─────────────────────────────────────


async def _handle_idle(ctx: AgentContext):
    """IDLE → just transition to THINKING."""
    ctx.metadata["next"] = "think"


async def _handle_thinking(ctx: AgentContext):
    """THINKING: call LLM, parse response, set flags on ctx.metadata."""
    # Import dependencies inside handler to avoid circular imports at module level
    from soul.personality import soul
    from tools.registry import registry
    from ui.status_bar import status as _status
    from ui import display as _display

    effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)
    
    # ─── OPTIMIZATION: Prompt Caching ───
    # We collect all dynamic context (RAG, learnings, first-turn hints) and 
    # append them to the LAST USER MESSAGE instead of the System Prompt.
    # This keeps the System Prompt 100% static across all turns, maximizing
    # cache hits on Anthropic/DeepSeek.
    dynamic_injections = []

    # RAG context injection
    try:
        from knowledge.rag_engine import rag
        rag_context = rag.context_for_query(ctx.user_input or "")
        if rag_context:
            dynamic_injections.append(rag_context)
    except Exception:
        pass  # RAG yoksa sessizce gec
    
    # P0-15: First-turn task detection
    _first_turn = loop.turn <= 1
    _user_msg = (ctx.user_input or "").lower()
    _has_task = any(w in _user_msg for w in ["oku", "yaz", "calistir", "duzelt", "guncelle", "bul", "ara", "goster", "listele", "read", "write", "run", "fix", "update", "find", "search", "show", "list"])
    _is_complex = any(w in _user_msg for w in ["proje", "uygulama", "sistem", "mimar", "yeniden", "refactor", "gelistir", "olustur", "project", "app", "system", "architect", "rewrite", "develop", "create"])
    
    # Basit bilgi sorusu tespiti
    _question_count = _user_msg.count("?")
    _is_simple_info = (
        any(w in _user_msg for w in ["nedir", "kimdir", "kaç", "kac", "nasil", "nasıl", "ne demek", "neden", "ne zaman", "kim", "nerede"])
        and not _has_task
        and not _is_complex
        and len(_user_msg.split()) <= 20
    ) or (
        # Matematik soruları
        any(op in _user_msg for op in ["+", "-", "*", "/", "kaçtır", "kactir", "topla", "çarp", "böl"])
        and len(_user_msg.split()) <= 10
    )

    _is_simple_info = _is_simple_info or (
        _question_count >= 2
        and not _has_task
        and not _is_complex
        and len(_user_msg.split()) <= 25
    )

    if _first_turn:
        if _is_complex:
            dynamic_injections.append("[SYSTEM: Bu karmaşık bir görev. Lütfen önce adım adım PLANINI (hangi dosyaları inceleyeceksin, hangi adımları izleyeceksin) normal metin (content) olarak yaz, ARDINDAN AYNI YANITTA planının İLK ADIMI için gereken aracı (tool_call) çalıştır.]")
        elif _has_task:
            dynamic_injections.append("[SYSTEM: Kullanici mesaji bir GOREV iceriyor. Selamlama yapma, tanisma muhabbeti yapma. DOGRUDAN tool cagir ve gorevi yap.]")
    
    loop._repair_message_sequence()

    ctx.metadata["planning_retry"] = False
    ctx.metadata["truncated"] = False
    ctx.metadata["finalized"] = False
    ctx.metadata["has_error"] = False

    # Update status
    _status.set_status("thinking")

    # P2-14: Load relevant learnings from past mistakes
    try:
        from evolution.self_check import get_relevant_learnings
        learnings = get_relevant_learnings(ctx.user_input or "")
        if learnings:
            log.debug("Past learnings injected into user message")
            dynamic_injections.append(learnings)
    except Exception:
        pass

    # Validate messages before sending & Inject dynamic context
    msgs = [msg.copy() for msg in loop.context.get_messages()]
    if dynamic_injections:
        # Find the last user message and append the dynamic injections
        for i in range(len(msgs)-1, -1, -1):
            if msgs[i].get("role") == "user":
                msgs[i]["content"] = msgs[i].get("content", "") + "\n\n" + "\n\n".join(dynamic_injections)
                break


    # Multi-persona review kaldirildi — gereksiz LLM cagrisi

    # Validate messages before sending (and fix any empty assistant msgs)
    for i, m in enumerate(msgs):
        if m.get("role") == "assistant" and not m.get("content") and not m.get("tool_calls"):
            log.warning(f"FIXING invalid assistant msg at idx {i}")
            msgs[i]["content"] = "(continuing...)"

    # P2-14: RAG-based tool selection — only pass relevant tools
    tool_schemas = []
    if _is_simple_info:
        # dynamic_injections'a değil, doğrudan effective_prompt'a ekle
        effective_prompt += "\n\n[KURAL: Bu soru doğrudan cevaplanabilir. Hiçbir tool çağırma, kendi bilgilerinle yanıtla.]"
        tool_schemas = []  # tool gönderme
        log.debug("Basit bilgi sorusu — tool yok")
    else:
        try:
            from tools.selector import selector as _sel
            if not getattr(_sel, '_indexed', False):
                await _sel.initialize()
            ctx_input = ctx.user_input or ""
            filtered = await _sel.schemas_for_context(ctx_input, top_k=15)
            if filtered:
                tool_schemas = filtered
                log.debug(f"ToolSelector: {len(filtered)} tools")
            else:
                log.debug("ToolSelector returned empty, using all tools")
                tool_schemas = registry.schemas()
        except Exception as _e:
            log.debug(f"Tool selection unavailable, using all tools: {_e}")
            tool_schemas = registry.schemas()

    try:
        from ui import display as _disp_stream

        # Onceki turda tum tool'lar basarisiz olduysa, alternatif strateji ekle
        if ctx.metadata.get("all_tools_failed"):
            effective_prompt += "\n\n[ALTERNATIF STRATEJI] Bir onceki adimda tool hata verdi. "
            effective_prompt += "Farkli bir tool dene veya ayni tool'u farkli parametrelerle dene. "
            effective_prompt += "Web aramasi calismadiysa: web_fetch ile dogrudan URL cekmeyi dene. "
            effective_prompt += "Terminal hata verdiyse: sudo ile veya farkli bir yontemle dene. "
            effective_prompt += "Pes etme, alternatif bul."
        
        _disp_stream.print_info("\u23f3 Dusunuyor...")

        def _on_chunk(chunk: str):
            _disp_stream.print_assistant_stream(chunk)

        response = await loop.reasoning.think(
            effective_prompt, msgs, tool_schemas,
            stream_callback=_on_chunk,
        )
        loop._streamed_this_turn = True
    except Exception as e:
        from core.error_classifier import classify_api_error, format_user_error
        from core.error_db import log_llm_error
        classified = classify_api_error(e, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
        user_msg = format_user_error(e, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
        log.error(f"LLM error: {classified.reason} — {e}")
        log_llm_error(str(e), category=classified.reason, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
        _display.print_assistant(user_msg)
        ctx.metadata["has_error"] = True
        return

    loop._update_status(response)
    
    # Iteration Budget — cok yuksek limit, sadece gercek sonsuz donguleri kirmak icin
    _tc = response.get("tool_calls", [])
    if _tc:
        ctx.iterations_used += 1
        if ctx.iterations_used >= 500:
            from ui import display as _disp_budget
            _disp_budget.print_error(f"Bütçe Tükendi! (Maksimum 500 iterasyon)")
            log.warning("Iteration budget exhausted, forcing exit.")
            ctx.metadata["has_tools"] = False
            ctx.metadata["finalized"] = True
            ctx.llm_response = {"content": "Sistem: Maksimum işlem bütçesi doldu. Görevi sonlandırıyorum."}
            return
    
    tool_calls = response.get("tool_calls", [])
    content = response.get("content", "")
    finish_reason = response.get("finish_reason", "stop")

    if content:
        content = loop._clean_content(content)

    # Handle truncated response
    if finish_reason == "length":
        log.warning("LLM response truncated (finish_reason=length)")
        loop.context.add_assistant_message(content or "(devam ediyor...)")
        if not tool_calls:
            loop.context.add_user_message("Devam et, cevabın kesildi. Kaldığın yerden devam et.")
            ctx.metadata["truncated"] = True
            return
        # If there are tool calls with truncated response, still process them
        ctx.metadata["has_tools"] = bool(tool_calls)
        ctx.metadata["truncated"] = True
        return

    ctx.metadata["has_tools"] = bool(tool_calls)
    # Stronger DONE detection: check if LLM is still planning
    _has_plan_words = any(
        word in content[:200].lower()
        for word in [
            "önce", "sonra", "ardından", "şimdi", "hemen", "başlıyorum",
            "first", "then", "next", "now", "let me", "let's start", "i'll",
            "devam", "sıra", "adım", "step", "şu şekilde",
        ]
    )
    _task_incomplete_signals = any(
        word in content.lower()
        for word in [
            "tree", "yapı", "structure", "keşfedeyim", "bakayım", "inceleyeyim",
            "hazırım", "başlıyorum", "devam", "şimdi", "next step",
        ]
    )
    # İlk 2 turda sadece keşif tool'ları çağrıldıysa finalized sayma
    _is_exploration_only = (
        ctx.turn <= 2
        and ctx.metadata.get("tool_call_count", 0) <= 2
    )
    # P0-15: First-turn greeting detection — if user gave a task but LLM just greeted, force re-think
    _greeting_retries = ctx.metadata.get("greeting_retry_count", 0)
    _is_greeting_without_tools = (
        ctx.turn <= 1
        and not tool_calls
        and _greeting_retries < 1
        and len((ctx.user_input or "").strip().split()) <= 3  # Sadece kisa selamlama
        and any(w in (ctx.user_input or "").lower() for w in ["merhaba", "selam", "hey", "hi", "hello", "naber"])
    )
    ctx.metadata["finalized"] = (
        not tool_calls
        and bool(content)
        and not _has_plan_words
        and not _task_incomplete_signals
        and not _is_exploration_only
        and not _is_greeting_without_tools
    )
    ctx.llm_response = response
    
    # P0-15: Greeting retry — if LLM greeted instead of doing the task, force a retry with stronger hint
    if _is_greeting_without_tools:
        ctx.metadata["greeting_retry_count"] = _greeting_retries + 1
        ctx.metadata["planning_retry"] = True  # stay in THINKING
        loop.context.add_assistant_message(content or "(devam...)")
        loop.context.add_user_message("READ THE FILE and FIX THE BUG. Use read_file tool, then patch tool. DO NOT greet.")
        ctx.turn = max(0, ctx.turn - 1)  # don't count this wasted turn


async def _handle_tool_calling(ctx: AgentContext):
    """TOOL_CALLING: extract tool_calls from last LLM response, build assistant msg."""
    from ui.status_bar import status as _status

    tool_calls = ctx.llm_response.get("tool_calls", [])
    content = ctx.llm_response.get("content", "")
    if not tool_calls:
        return

    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.get("id", f"call_{tc['function']['name']}"),
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            }
            for tc in tool_calls
        ],
    }
    loop.context.messages.append(assistant_msg)
    ctx.tool_calls = tool_calls
    _status.add_tool_call()
    # Update status bar with tool name
    if tool_calls:
        tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        _status.set_status(f"tool: {', '.join(tool_names)}")


async def _handle_waiting_result(ctx: AgentContext):
    """WAITING_RESULT: execute tools, add results to context. Partial success → synthesize."""
    from tools.executor import executor
    from tools.registry import registry
    from ui import display as _display
    from ui.status_bar import status as _status

    tool_calls = ctx.tool_calls
    if not tool_calls:
        ctx.metadata["all_tools_failed"] = True
        return

    READ_TOOLS = frozenset({"read_file", "search_files", "web_search", "web_fetch", "browser_snapshot", "gif_search", "list_directory"})
    read_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") in READ_TOOLS]
    write_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") not in READ_TOOLS]

    success_count = 0
    fail_count = 0

    async def _run_one(tc):
        nonlocal success_count, fail_count
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", "{}")
        tool_call_id = tc.get("id", f"call_{name}")
        _status.add_tool_call()
        # Flush any remaining stream buffer before printing tool name
        from ui.display import flush_stream as _flush_stream
        _flush_stream()
        _display.print_tool_start(name, None)
        try:
            if name in READ_TOOLS:
                result = await asyncio.to_thread(executor.execute, name, args)
            else:
                result = await asyncio.to_thread(executor.execute, name, args)
            loop.context.add_tool_result(name, result, tool_call_id)
            if "error" in result[:20].lower():
                _display.print_tool_error(name, result)
                fail_count += 1
            else:
                _display.print_tool_done(name, result)
                success_count += 1
                
                # --- Self-Review & Auto-Testing ---
                if name in ("write_file", "patch"):
                    import os
                    import json
                    
                    # 1. Self-Review (Kontrol Katmanı)
                    try:
                        _needs_review = False
                        _code_to_review = ""
                        
                        if name == "patch":
                            res_obj = json.loads(result)
                            _verif = res_obj.get("verification", {}).get("changed_lines", [])
                            if len(_verif) >= 5:
                                _needs_review = True
                                _code_to_review = "\n".join(str(v) for v in _verif)
                        elif name == "write_file":
                            _args_obj = json.loads(args)
                            _code_to_review = _args_obj.get("content", "")
                            if len(_code_to_review.split("\n")) > 10:
                                _needs_review = True
                                
                        if _needs_review and _code_to_review:
                            _display.print_info("Büyük değişiklik tespit edildi, otomatik test çalıştırılıyor...")
                            # Self-review kaldirildi, sadece test sonuclarina guven
                    except Exception as _e:
                        pass

                    # 2. Auto-Test
                    _display.print_info("Otomatik test çalıştırılıyor...")
                    test_cmd = "python -m pytest tests/ -q --tb=short 2>&1 | tail -n 15"
                    test_args = json.dumps({"command": test_cmd})
                    test_result = await asyncio.to_thread(executor.execute, "terminal", test_args)
                    if "failed" in test_result.lower() or "error" in test_result.lower() or "traceback" in test_result.lower():
                        loop.context.add_user_message(
                            f"[OTOMATIK TEST BAŞARISIZ]\nAz önce yaptığın '{name}' işlemi testleri bozdu veya hata verdi. "
                            f"Lütfen analiz edip hatayı düzelt:\n\n{test_result}"
                        )
                        _display.print_tool_error("auto_test", "Testler patladı! Otonom kurtarma başlıyor...")
                    else:
                        _display.print_success("Auto-Test: Başarılı 🚀")
        except Exception as e:
            loop._handle_tool_error(name, e, tool_call_id)
            fail_count += 1

    # Read tools in parallel
    if read_calls:
        await asyncio.gather(*[_run_one(tc) for tc in read_calls])
    # Write tools sequentially
    for tc in write_calls:
        await _run_one(tc)

    ctx.metadata["all_tools_failed"] = (success_count == 0 and fail_count > 0)
    ctx.metadata["tool_call_count"] = ctx.metadata.get("tool_call_count", 0) + success_count + fail_count

    # P2-14: Auto-dependency resolution — if tools failed, try to find and install missing deps
    if fail_count > 0 and success_count == 0:
        try:
            # Collect error messages to search for solutions
            _error_msgs = []
            for m in loop.context.get_messages()[-fail_count * 2:]:
                if m.get("role") == "tool":
                    _error_msgs.append(str(m.get("content", ""))[:200])
            if _error_msgs:
                _search_query = " ".join(_error_msgs[-2:])[:200]
                _search_result = await asyncio.to_thread(
                    executor.execute, "web_search",
                    '{"query": "' + _search_query.replace('"', "'") + '"}'
                )
                # Extract install command from search results
                _install_cmd = None
                for _kw in ["pip install", "apt install", "pacman -S", "npm install", "brew install", "cargo install", "dnf install", "yay -S"]:
                    if _kw in _search_result.lower():
                        # Extract the actual command
                        import re as _re
                        _match = _re.search(r'(' + _kw + r'[^\n.]*)', _search_result)
                        if _match:
                            _install_cmd = _match.group(1).strip()
                            break
                if _install_cmd:
                    _display.print_info(f"Kurulum: {_install_cmd}")
                    executor.execute("terminal", '{"command": "' + _install_cmd.replace('"', "'") + '"}')
                    ctx.metadata["auto_repaired"] = True
                    log.info(f"Auto-resolved: {_install_cmd}")
        except Exception as _dep_e:
            log.debug(f"Auto-dependency resolution failed: {_dep_e}")

    # P2-13: Auto-checkpoint
    from orchestrator.checkpoint import checkpoint_manager as _cp
    _cp.update_turn(ctx.turn)
    if _cp.should_checkpoint:
        await _cp.save({"turn": ctx.turn, "state": "thinking", "messages": loop.context.get_messages()}, cp_type="auto")


async def _handle_synthesize(ctx: AgentContext):
    """SYNTHESIZE: ask LLM for final summary without tools."""
    from soul.personality import soul
    from ui import display as _display
    effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)
    final = await loop.reasoning.think(effective_prompt, loop.context.get_messages(), [])
    content = final.get("content", "")
    if content:
        content = loop._clean_content(content)
        loop.context.add_assistant_message(content)
        ctx.final_response = content
    else:
        ctx.final_response = "Task completed. Use /help for available commands."


async def _handle_direct_reply(ctx: AgentContext):
    """DIRECT_REPLY: clean up tool messages, add final assistant message."""
    content = ctx.llm_response.get("content", "")
    if content:
        content = loop._clean_content(content)
        cleaned = []
        for m in loop.context.get_messages():
            role = m.get("role", "")
            if role == "tool":
                continue
            if role == "assistant" and m.get("tool_calls"):
                continue
            cleaned.append(m)
        loop.context.messages = cleaned
        loop.context.add_assistant_message(content)
        ctx.final_response = content
    else:
        ctx.final_response = "Task completed."


async def _handle_error(ctx: AgentContext):
    """ERROR: log, display user message."""
    from ui import display as _display
    msg = f"Bir hata oluştu: {ctx.error or 'Bilinmeyen hata'}"
    log.error(msg)
    _display.print_assistant(msg)


async def _handle_done(ctx: AgentContext):
    """DONE: final response is already in ctx.final_response. Clean up."""
    if not ctx.final_response:
        from soul.personality import soul

        effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)
        final = await loop.reasoning.think(effective_prompt, loop.context.get_messages(), [])
        content = final.get("content", "")
        if content:
            content = loop._clean_content(content)
            loop.context.add_assistant_message(content)
            ctx.final_response = content
        else:
            ctx.final_response = "Task completed."

    if ctx.error:
        log.info(f"Session completed with error: {ctx.error}")


async def _handle_fallback(ctx: AgentContext):
    """FALLBACK: retry thinking after error/abort."""
    ctx.metadata["has_error"] = False

