"""SYNTHESIZE, DIRECT_REPLY, DONE, IDLE, ERROR, FALLBACK handlers."""

from __future__ import annotations
from orchestrator.state_machine import AgentContext
from core.logger import log


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
        content = loop._clean_content(content)
        loop.context.add_assistant_message(content)
        ctx.final_response = content
    else:
        ctx.final_response = "Task completed. Use /help for available commands."


async def handle_direct_reply(loop, ctx: AgentContext):
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


async def handle_error(loop, ctx: AgentContext):
    """ERROR: log, display user message."""
    from ui import display as _display
    msg = f"Bir hata oluştu: {ctx.error or 'Bilinmeyen hata'}"
    log.error(msg)
    _display.print_assistant(msg)


async def handle_done(loop, ctx: AgentContext):
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


async def handle_fallback(loop, ctx: AgentContext):
    """FALLBACK: retry thinking after error/abort."""
    ctx.metadata["has_error"] = False
