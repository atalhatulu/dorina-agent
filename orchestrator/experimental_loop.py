"""
AgentLoopV2 — sade 2-katmanli agent loop.

Think → Act dongusu. Claude Code'un basit yaklasimi + Dorina'nin pratik limitleri.

Farklar (eski AgentLoop'a gore):
  - State machine yok (while loop)
  - Event bus yok
  - Handler zinciri yok
  - repair_message_sequence her turda degil, sadece tool sonrasi
  - Session save background task
  - 3 tool/turn sert limit
  - Read paralel, write sirali
  - LRU read_file cache (20)
  - Self-reflection: 3+ ayni hata → strategy change
  - Context compression token esiginde
"""

from __future__ import annotations
from typing import Optional
import asyncio
import json
from collections import OrderedDict
from pathlib import Path

from core.logger import log
from core.constants import MAX_TURNS
from orchestrator.reasoning import ReasoningEngine
from orchestrator.context import Context
from orchestrator.compressor import ContextCompressor
from orchestrator.cleaner import clean_content
from orchestrator.greeting import is_greeting
from orchestrator.titler import autotitle
from orchestrator.repair import repair_message_sequence
from core.tokenizer import count_messages_tokens
from core.error_classifier import classify_api_error, sanitize_tool_error
from core.error_db import log_tool_error, log_error_pattern, get_frequent_patterns
from core.mode_manager import modes
from tools.selector import select_schemas
from tools.registry import registry
from tools.executor import executor
from soul.personality import soul
from session.manager import manager as session_manager

# ── Lazy UI imports (prompt_toolkit may not be in test env) ─────
class _NullUI:
    """No-op fallback — all calls succeed silently."""
    def __getattr__(self, _name):
        return _null_noop

def _null_noop(*_args, **_kwargs):
    return None

try:
    from ui.status_bar import status as _status
except ImportError:
    _status = _NullUI()

try:
    from ui import display as _display
except ImportError:
    _display = _NullUI()

# ── Proaktif read_file cache ──────────────────────────────────────
_FILE_CACHE: OrderedDict[str, str] = OrderedDict()
_FILE_CACHE_MAX = 20

def _cache_get(path: str) -> str | None:
    resolved = str(Path(path).resolve())
    if resolved not in _FILE_CACHE:
        return None
    _FILE_CACHE.move_to_end(resolved)
    return _FILE_CACHE[resolved]

def _cache_set(path: str, content: str):
    resolved = str(Path(path).resolve())
    _FILE_CACHE[resolved] = content
    _FILE_CACHE.move_to_end(resolved)
    while len(_FILE_CACHE) > _FILE_CACHE_MAX:
        _FILE_CACHE.popitem(last=False)

def _cache_invalidate(paths: list[str]):
    for p in paths:
        key = str(Path(p).resolve())
        _FILE_CACHE.pop(key, None)

# ── Read-only tool set (paralel calisabilir) ──────────────────────
_READ_TOOLS = frozenset({
    "read_file", "search_files", "web_search", "web_fetch",
    "browser_snapshot", "gif_search", "list_directory",
})

# ── Loop iteration limit ──────────────────────────────────────────
# 3 tool/turn × 50 = 150 tool call / kullanici mesaji. Fazlasi anomaly.
_MAX_LOOP_ITERATIONS = 50


class AgentLoopV2:
    """2-katmanli agent loop: think → act.

    Kullanim:
        loop = AgentLoopV2()
        response = await loop.process("dosyayi oku")
    """

    def __init__(self):
        self.reasoning = ReasoningEngine()
        self.context = Context()
        self.turn = 0
        self.compressor = ContextCompressor()
        self._skills_injected = False
        self._session_titled = False
        self._system_prompt: str = soul.system_prompt
        self._consecutive_llm_errors = 0
        self._error_patterns: dict[str, list] = {}
        self._temp_mode = False
        self._loop_iterations = 0

    # ────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ────────────────────────────────────────────────────────────────

    async def process(self, user_input: str) -> str:
        """Think → act dongusu.

        1. Greeting kontrolu (LLM cagrisi yok)
        2. System prompt hazirlik (ilk tur: title, skill, RAG)
        3. Think → Act loop
        """
        # ── 0. GIRIS KONTROLLERI ───────────────────────────────────

        if is_greeting(user_input):
            return self._handle_greeting(user_input)

        user_input = self._sanitize(user_input)

        if self.turn >= MAX_TURNS:
            _status.set_status("idle")
            return "Maximum turns reached. Use /new to reset."

        self.turn += 1
        self._loop_iterations = 0
        _status.start_turn()
        self._streamed_this_turn = False

        # ── 1. PREPARE (ilk tur): title + system prompt ────────────
        if self.turn == 1 and not self._session_titled:
            title = autotitle(user_input, session_id=session_manager.current_id)
            self._session_titled = bool(title)

        if not self._skills_injected:
            self._build_system_prompt(user_input)

        self.context.add_user_message(user_input)

        # Tool secimi — tum loop boyunca ayni set
        tool_names = select_schemas(user_input, registry)
        tool_schemas = registry.schemas_for(tool_names) if tool_names else []

        # ── 2. THINK → ACT LOOP ────────────────────────────────────
        while self._loop_iterations < _MAX_LOOP_ITERATIONS:
            self._loop_iterations += 1

            # Context compression (sadece %75 dolulukta)
            if self.compressor.should_compress(self.context.get_messages()):
                compressed = await self.compressor.compress(
                    self.context.get_messages(), self._summarize
                )
                self.context.messages = compressed

            # Eski read_file sonuclarini buda
            self._trim_old_read_file_results()

            # Think: LLM cagrisi
            response = await self._think(tool_schemas)

            # Status: token kullanimi
            self._update_status(response)

            # Budget asimi → force compression + retry
            if response.get("_budget_breached"):
                _display.print_warning("Token budget asildi! Compression basliyor...")
                compressed = await self.compressor.compress(
                    self.context.get_messages(), self._summarize
                )
                self.context.messages = compressed
                continue

            tool_calls = response.get("tool_calls", [])
            content = response.get("content", "")

            # Truncated response (finish_reason == "length")
            if response.get("finish_reason") == "length":
                self.context.add_assistant_message(content or "(devam ediyor...)")
                if not tool_calls:
                    self.context.add_user_message(
                        "Devam et, cevabin kesildi."
                    )
                    continue
                # Tool calls + truncated: yine de tool'lari isle

            # Empty response retry
            if not tool_calls and not content:
                log.warning("LLM returned empty response — retrying")
                self.context.add_assistant_message("(bos yanit)")
                self.context.add_user_message(
                    "Onceki aracin sonucunu degerlendir ve devam et."
                )
                continue

            # Act: tool varsa calistir, degilse yanit
            if tool_calls:
                self._add_tool_call_message(tool_calls)
                await self._execute_tools(tool_calls)
                self.context.messages = repair_message_sequence(self.context.messages)
                continue

            # Yanit — is bitti
            content = clean_content(content)
            self.context.add_assistant_message(content)
            self._schedule_save(content)
            self._consecutive_llm_errors = 0
            return content

        log.warning("AgentLoopV2: iteration budget exhausted (%d)", _MAX_LOOP_ITERATIONS)
        _display.print_error("Maksimum islem butcesi doldu.")
        return "Maximum iterations reached."

    # ────────────────────────────────────────────────────────────────
    # SYSTEM PROMPT HAZIRLIGI (ilk tur)
    # ────────────────────────────────────────────────────────────────

    def _build_system_prompt(self, user_input: str):
        """System prompt'u hazirla: skill injection + RAG + evolution."""
        sections = []

        # 1. Skill injection
        try:
            from skills.manager import skills as _mgr
            active = _mgr.get_applicable_skills(user_input)
        except (ImportError, AttributeError, ValueError):
            active = []

        if active:
            skill_blocks = []
            for s in active:
                content = s["content"]
                if isinstance(content, dict):
                    content = content.get("content", "") or str(content)
                if len(content) > 500:
                    content = content[:500] + (
                        f"\n[...{len(content)-500} karakter daha, "
                        f"/skills {s['name']} ile tamami]"
                    )
                skill_blocks.append(f"## Skill: {s['name']} ({s['trigger']})\n{content}")
            sections.append("### Loaded Skills\n" + "\n\n".join(skill_blocks))
            log.info("Skills injected: %s", [s["name"] for s in active])

        # 2. RAG context
        try:
            from knowledge.rag_engine import rag
            rag_context = rag.context_for_query("")
            if rag_context:
                sections.append(rag_context)
        except (ImportError, AttributeError, ValueError):
            pass

        # 3. Evolution learnings
        try:
            from evolution.self_check import get_relevant_learnings
            learnings = get_relevant_learnings("")
            if learnings:
                sections.append(learnings)
        except (ImportError, OSError, ValueError):
            pass

        # Kisa prompt mu?
        _simple_words = {
            "merhaba", "selam", "hey", "naber", "nasilsin",
            "gunaydin", "kolay gelsin", "ne haber",
        }
        _input_lower = (user_input or "").lower().strip().rstrip(".!?,")
        if (
            modes.is_on("speed")
            or _input_lower in _simple_words
            or len((user_input or "").split()) <= 3
        ):
            base = soul.system_prompt_short
        else:
            base = soul.system_prompt

        if sections:
            self._system_prompt = base + "\n\n---\n" + "\n\n".join(sections)
        else:
            self._system_prompt = base

        self._skills_injected = True

    # ────────────────────────────────────────────────────────────────
    # THINK: LLM CAGRISI
    # ────────────────────────────────────────────────────────────────

    async def _think(self, tool_schemas: list[dict]) -> dict:
        """LLM cagrisi. Hata durumunda cooldown + retry."""
        _status.set_status("thinking")

        msgs = self.context.get_messages()

        try:
            response = await self.reasoning.think(
                self._system_prompt, msgs, tool_schemas
            )
            self._consecutive_llm_errors = 0
            return response
        except (RuntimeError, ConnectionError, TimeoutError,
                ValueError, json.JSONDecodeError) as e:
            self._consecutive_llm_errors += 1
            log.error("LLM error (x%d): %s", self._consecutive_llm_errors, e)
        except Exception as e:
            self._consecutive_llm_errors += 1
            log.warning("Unexpected LLM error type (%s): %s", type(e).__name__, e)

        if self._consecutive_llm_errors >= 3:
            _display.print_error(
                "LLM 3 kez hata verdi. /provider ile degistir veya tekrar dene."
            )
            return {"content": "", "tool_calls": [], "finish_reason": "error"}

        # Cooldown: 0.5s → 1s → 2s → 4s → 8s → 16s → 30s
        delay = min(0.5 * (2 ** (self._consecutive_llm_errors - 1)), 30)
        _display.print_info(
            f"LLM hatasi, {delay:.0f}s bekleniyor... "
            f"(ardisik: {self._consecutive_llm_errors})"
        )
        await asyncio.sleep(delay)

        # Retry mesaji ekle ve recursive dene
        self.context.add_user_message(
            "Bir onceki LLM cagrisi hata verdi. Tekrar dene."
        )
        return await self._think(tool_schemas)

    # ────────────────────────────────────────────────────────────────
    # ACT: TOOL EXECUTION
    # ────────────────────────────────────────────────────────────────

    def _add_tool_call_message(self, tool_calls: list[dict]):
        """Assistant(tool_calls) mesaji ekle."""
        self.context.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name", "unknown"),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    },
                }
                for tc in tool_calls
            ],
        })

    async def _execute_tools(self, tool_calls: list[dict]):
        """Tool'lari calistir. Read paralel, write sirali."""
        # Enforce max 3 per turn
        if len(tool_calls) > 3:
            trimmed = tool_calls[3:]
            trimmed_names = [
                tc.get("function", {}).get("name", "?") for tc in trimmed
            ]
            _display.console.print(
                f"[bold yellow]"
                f"Tek turda max 3 tool ({len(tool_calls)} istendi). "
                f"Ilk 3 calisiyor.[/]"
            )
            self.context.add_assistant_message(
                f"[SISTEM] {len(trimmed_names)} tool kirpildi (limit: 3/tur): "
                f"{', '.join(trimmed_names)}. Kalanlari sonraki turda cagirabilirsin."
            )
            tool_calls = tool_calls[:3]

        # Repetition guard: ayni dosyayi ayni turda 2. kez okuma
        seen_in_turn: set = set()
        filtered = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            if name == "read_file":
                args = _parse_tool_args(fn.get("arguments", "{}"))
                path = args.get("path", "") if args else ""
                if path and path in seen_in_turn:
                    _display.console.print(
                        f"[dim]{path} ayni turda 2. kez okunuyor, atlandi[/]"
                    )
                    continue
                seen_in_turn.add(path)
            filtered.append(tc)

        # Ayristir: read vs write
        read_calls = [tc for tc in filtered
                      if tc.get("function", {}).get("name", "") in _READ_TOOLS]
        write_calls = [tc for tc in filtered
                       if tc.get("function", {}).get("name", "") not in _READ_TOOLS]

        async def _run_one(tc: dict):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args_raw = fn.get("arguments", "{}")
            tool_call_id = tc.get("id", f"call_{name}")

            _status.add_tool_call()
            _display.flush_stream()

            parsed_args = _parse_tool_args(args_raw)
            _display.print_tool_start(name, parsed_args)

            try:
                # Cache: read_file kontrol
                if name == "read_file" and parsed_args:
                    read_path = parsed_args.get("path", "")
                    cached = _cache_get(read_path)
                    if cached is not None:
                        self.context.add_tool_result(name, cached, tool_call_id)
                        _display.print_tool_done(name, cached)
                        return

                result = await executor.async_execute_json(name, args_raw)

                # Cache store/update
                if name == "read_file" and parsed_args:
                    read_path = parsed_args.get("path", "")
                    if read_path and "error" not in result[:20].lower():
                        _cache_set(read_path, result)

                if name in ("write_file", "patch") and parsed_args:
                    target = parsed_args.get("path", parsed_args.get("target", ""))
                    if target and "error" not in result[:20].lower():
                        _cache_invalidate([target])

                self.context.add_tool_result(name, result, tool_call_id)

                if "error" in result[:20].lower():
                    _display.print_tool_error(name, result)
                else:
                    _display.print_tool_done(name, result)
                    if not self._temp_mode:
                        self._schedule_save(f"[{name}] {result[:100]}", quick=True)

            except (ValueError, json.JSONDecodeError, RuntimeError, OSError) as e:
                self._handle_tool_error(name, e, tool_call_id)
            except Exception as e:
                log.warning("Unexpected tool error type (%s): %s", type(e).__name__, e)
                self._handle_tool_error(name, e, tool_call_id)

        # Read paralel, write sirali
        if read_calls:
            await asyncio.gather(*[_run_one(tc) for tc in read_calls])
        for tc in write_calls:
            await _run_one(tc)

    # ────────────────────────────────────────────────────────────────
    # ERROR HANDLING
    # ────────────────────────────────────────────────────────────────

    def _handle_tool_error(self, name: str, error: Exception, tool_call_id: str):
        """Tool hatasi + self-reflection."""
        classified = classify_api_error(error)
        safe_reason = str(classified.reason)

        log.error("Tool error [%s]: %s — %s", name, safe_reason, error)
        _display.print_tool_error(name, safe_reason + ": " + str(error))

        sanitized = sanitize_tool_error(str(error))
        self.context.add_tool_result(name, sanitized, tool_call_id)
        log_tool_error(tool_name=name, error=error)

        # Self-reflection: error pattern tracking (memory + DB)
        sig = f"{name}:{classified.reason}"
        prev = self._error_patterns.get(sig, [sig, 0])
        prev[1] += 1
        self._error_patterns[sig] = prev
        log_error_pattern(name, classified.reason, str(error))

        # Hafizadan eski cozum
        try:
            from evolution.self_check import get_relevant_learnings
            past = get_relevant_learnings(str(error))
            if past:
                self.context.add_user_message(
                    f"[HAFIZA] Bu hatayi gecmiste yasadik. Ders:\n{past}"
                )
                _display.print_info("Gecmiste benzer hata bulundu.")
        except (ImportError, KeyError, AttributeError):
            pass

        # 3+ ayni hata → strategy change
        if prev[1] >= 3:
            log.warning("Self-reflection: %s repeated %dx — forcing strategy change", sig, prev[1])
            self.context.add_user_message(
                f"[SELF-REFLECTION] '{name}' araci {prev[1]} kez ayni hatayi "
                f"verdi: {classified.reason}. Bu araci tekrar kullanma. "
                f"Farkli bir yaklasim dene."
            )
            self._error_patterns[sig][1] = 0

    # ────────────────────────────────────────────────────────────────
    # YARDIMCILAR
    # ────────────────────────────────────────────────────────────────

    def _handle_greeting(self, user_input: str) -> str:
        """Selamlari Python tarafinda cevapla (LLM yok)."""
        _status.set_status("idle")
        self.turn = max(0, self.turn - 1)

        text = (user_input or "").lower().strip().rstrip(".!?,")
        words = set(text.split())
        ad = ""
        skip_words = {
            "merhaba", "selam", "hey", "hi", "hello", "naber",
            "nasilsin", "nasılsın", "gunaydin", "günaydın",
            "iyi geceler", "kolay gelsin", "ne haber", "dorina",
        }
        for w in words:
            if w not in skip_words:
                ad = w
                break

        selam_sozu = "Merhaba" if "merhaba" in text else "Selam"
        yanit = f"{selam_sozu}{' ' + ad.title() if ad else ''}! Sana nasil yardimci olabilirim?"
        self.context.add_assistant_message(yanit)
        return yanit

    @staticmethod
    def _sanitize(text: str) -> str:
        """Surrogate + kontrol karakterlerini temizle."""
        import re
        if not text:
            return text
        text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        return text

    def _trim_old_read_file_results(self):
        """Son 10 mesaj disindaki read_file sonuclarini buda."""
        msgs = self.context.get_messages()
        if len(msgs) <= 4:
            return
        for msg in msgs[:-10]:
            if (
                msg.get("role") == "tool"
                and msg.get("name") == "read_file"
                and len(str(msg.get("content", ""))) > 200
            ):
                msg["content"] = "[okundu]"

    @staticmethod
    def _update_status(response: dict):
        """Token kullanimini status bar'a ekle."""
        usage = response.get("usage", {})
        _status.add_tokens(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cost=response.get("cost", 0),
        )

    def _schedule_save(self, summary: str = "", quick: bool = False):
        """Session save'i background task olarak baslat."""
        if self._temp_mode:
            return
        try:
            from core.config import settings
            if not settings.session.auto_save:
                return
        except (ImportError, AttributeError):
            pass
        messages = self.context.get_messages()
        asyncio.ensure_future(self._do_save(messages, summary, quick))

    async def _do_save(self, messages: list[dict], summary: str = "", quick: bool = False):
        try:
            if quick:
                session_manager.save(messages, summary=summary)
            else:
                session_manager.save(messages, summary=summary,
                                     token_total=count_messages_tokens(messages))
        except (ImportError, OSError, KeyError, AttributeError) as e:
            log.warning("Session save failed: %s", e)

    async def _summarize(self, messages_text: str) -> str:
        """Context compression icin ozet."""
        result = await self.reasoning.think(
            "You summarize conversations. Be concise.",
            [{"role": "user", "content": messages_text}],
        )
        return result.get("content", messages_text[:500])

    # ────────────────────────────────────────────────────────────────
    # RESET / CLEANUP
    # ────────────────────────────────────────────────────────────────

    def reset(self):
        """Yeni session icin sifirla."""
        from core.mode_manager import modes as _modes
        _modes.reset()
        self.turn = 0
        self.context.clear()
        self.compressor.reset()
        executor.reset_count()
        _status.reset()
        self._skills_injected = False
        self._session_titled = False
        self._system_prompt = soul.system_prompt
        self._consecutive_llm_errors = 0
        self._error_patterns.clear()
        self._loop_iterations = 0
        self._temp_mode = False
        import soul.personality as sp
        sp.SUDO_PASSWORD = ""

    async def cleanup(self):
        """Kaynaklari temizle."""
        if session_manager.current_id and self.context.get_messages():
            try:
                messages = self.context.get_messages()
                tool_calls_data = []
                for m in messages:
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            fn = tc.get("function", {})
                            tool_calls_data.append({
                                "name": fn.get("name", "?"),
                                "args_preview": str(fn.get("arguments", ""))[:100],
                            })
                token_total = count_messages_tokens(messages)
                from session.exporter import export_session
                from core.config import settings
                from core.constants import DEFAULT_MODEL
                export_session(
                    session_id=session_manager.current_id,
                    messages=messages,
                    summary="",
                    title="",
                    model=(
                        settings.model.active_model
                        or settings.model.default
                        or DEFAULT_MODEL
                    ),
                    tool_calls_data=tool_calls_data,
                    token_total=token_total,
                )
            except (ImportError, OSError, KeyError, json.JSONDecodeError) as e:
                log.error("Session export failed: %s", e)

        if session_manager.db:
            session_manager.db.close()
        log.info("Session DB closed")
        _status.reset()
        log.info("Agent reset")

        try:
            import litellm
            await litellm.close_litellm_async_clients()
        except (ImportError, AttributeError, OSError):
            pass


# ── Module-level helpers ─────────────────────────────────────────

def _parse_tool_args(args_raw: str | dict) -> dict | None:
    """Tool argument'ini JSON parse et. Hata durumunda None."""
    if isinstance(args_raw, dict):
        return args_raw
    try:
        return json.loads(args_raw)
    except (json.JSONDecodeError, TypeError):
        return None


# Global instance
loop_v2 = AgentLoopV2()
