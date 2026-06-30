"""THINKING handler — call LLM, parse response, decide next action."""

from __future__ import annotations
from core.logger import log
from orchestrator.state_machine import AgentContext


async def handle_thinking(loop, ctx: AgentContext):
    """Call LLM, parse response, set flags on ctx.metadata."""
    from soul.personality import soul
    from tools.registry import registry
    from ui.status_bar import status as _status
    from ui import display as _display

    effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)

    # ─── OPTIMIZATION: Prompt Caching ───
    # Collect all dynamic context (RAG, learnings, first-turn hints) and
    # append them to the LAST USER MESSAGE instead of the System Prompt.
    # This keeps the System Prompt 100% static across all turns, maximizing
    # cache hits on Anthropic/DeepSeek.
    dynamic_injections = []

    # RAG context injection (sadece anlamli kullanim girdisi varsa)
    _raw_input = (ctx.user_input or "").strip()
    if _raw_input:
        try:
            from knowledge.rag_engine import rag
            rag_context = rag.context_for_query(_raw_input)
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

    # Validate messages before sending (and fix any empty assistant msgs)
    for i, m in enumerate(msgs):
        if m.get("role") == "assistant" and not m.get("content") and not m.get("tool_calls"):
            log.warning(f"Repairing invalid assistant msg at idx {i}")
            msgs[i]["content"] = "(continuing...)"

    # Call LLM — sadece aktif toolset'lerin tool'larini gonder
    from tools.toolset import get_active_schemas
    tool_schemas = get_active_schemas()
    response = await loop.reasoning.think(effective_prompt, msgs, tool_schemas)
    _status.set_status("processing")

    # Update token usage from LLM response
    loop._update_status(response)

    # ─── Response Analysis ──────────────────────────────────────────────
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
        ctx.llm_response = response
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
    # P0-15: First-turn greeting detection
    _greeting_retries = ctx.metadata.get("greeting_retry_count", 0)
    _is_greeting_without_tools = (
        ctx.turn <= 1
        and not tool_calls
        and _greeting_retries < 1
        and len((ctx.user_input or "").strip().split()) <= 3
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

    # P0-15: Greeting retry — if LLM greeted instead of doing the task, force a retry
    if _is_greeting_without_tools:
        ctx.metadata["greeting_retry_count"] = _greeting_retries + 1
        ctx.metadata["planning_retry"] = True  # stay in THINKING
        loop.context.add_assistant_message(content or "(devam...)")
        loop.context.add_user_message("READ THE FILE and FIX THE BUG. Use read_file tool, then patch tool. DO NOT greet.")
        ctx.turn = max(0, ctx.turn - 1)  # don't count this wasted turn
