"""SYNTHESIZE, DIRECT_REPLY, DONE, IDLE, ERROR, FALLBACK handlers."""

from __future__ import annotations
from orchestrator.state_machine import AgentContext
from core.logger import log
from orchestrator.cleaner import clean_content


async def handle_idle(loop, ctx: AgentContext):
    """IDLE → just transition to THINKING."""
    ctx.metadata["next"] = "think"


async def handle_synthesize(loop, ctx: AgentContext):
    """SYNTHESIZE: ask LLM for final summary without tools."""
    from soul.personality import soul
    effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)
    final = await loop.reasoning.think(effective_prompt, loop.context.get_messages(), [])
    content = final.get("content", "")
    if content:
        content = clean_content(content)
        loop.context.add_assistant_message(content)
        ctx.final_response = content
    else:
        ctx.final_response = "Task completed. Use /help for available commands."


async def handle_direct_reply(loop, ctx: AgentContext):
    """DIRECT_REPLY: clean up tool messages, add final assistant message."""
    # Başarılı yanıt — consecutive LLM error counter'ı sıfırla
    loop._consecutive_llm_errors = 0
    content = ctx.llm_response.get("content", "")
    if content:
        content = clean_content(content)
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


async def handle_error(loop, ctx: AgentContext):
    """ERROR: show user-friendly error message, log to file."""
    from ui import display as _display
    from core.error_classifier import format_user_error
    _user_msg = format_user_error(ctx.error or "Bilinmeyen hata")
    _display.console.print(f"\n[bold #D4622A]✗ Bir hata oluştu[/bold #D4622A]")
    _display.console.print(_user_msg)
    _display.console.print("[dim]Detaylar: ~/.dorina/logs/agent.log[/dim]")
    log.error("Agent error: %s", ctx.error)


async def handle_done(loop, ctx: AgentContext):
    """DONE: final response is already in ctx.final_response. Clean up.

    Resets consecutive error counter on successful completion.
    """
    # Başarılı tur — consecutive LLM error counter'ı sıfırla
    loop._consecutive_llm_errors = 0
    if not ctx.final_response:
        from soul.personality import soul
        effective_prompt = getattr(loop, '_enriched_system_prompt', soul.system_prompt)
        final = await loop.reasoning.think(effective_prompt, loop.context.get_messages(), [])
        content = final.get("content", "")
        if content:
            content = clean_content(content)
            loop.context.add_assistant_message(content)
            ctx.final_response = content
        else:
            ctx.final_response = "Task completed."

    if ctx.error:
        log.info(f"Session completed with error: {ctx.error}")


async def handle_fallback(loop, ctx: AgentContext):
    """FALLBACK: retry thinking after error/abort with cooldown.

    Consecutive errors trigger exponential backoff to prevent
    rapid-fire spawn loops when LLM is down.
    """
    ctx.metadata["has_error"] = False
    ctx.error = None

    # Cooldown: consecutive hatalarda bekleme süresi ekle
    _consecutive = getattr(loop, '_consecutive_llm_errors', 0) + 1
    loop._consecutive_llm_errors = _consecutive

    if _consecutive > 1:
        import asyncio as _a
        _delay = min(2 ** (_consecutive - 1), 30)  # 2sn, 4sn, 8sn, 16sn, 30sn max
        log.warning(f"Cooldown: {_delay}s bekleniyor (consecutive_errors={_consecutive})")
        from ui import display as _disp
        _disp.print_info(f"⏳ Hata sonrası bekleme: {_delay}s... (ardışık: {_consecutive})")
        await _a.sleep(_delay)
    else:
        # İlk hata: kısa bir bekleme
        import asyncio as _a
        await _a.sleep(0.5)
