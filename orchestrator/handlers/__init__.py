"""State machine handlers — each accepts (loop, ctx) and returns None (async)."""

from __future__ import annotations
from typing import Callable
from orchestrator.state_machine import AgentContext


def build_handlers(loop) -> dict[str, Callable]:
    """Build the handler dict for state_machine.run(), wrapping each handler
    with the AgentLoop instance via closure."""
    from orchestrator.handlers.thinking_handler import handle_thinking
    from orchestrator.handlers.tool_handler import handle_tool_calling, handle_waiting_result
    from orchestrator.handlers.reply_handler import (
        handle_idle, handle_synthesize, handle_direct_reply,
        handle_error, handle_done, handle_fallback,
    )

    return {
        "idle": lambda ctx: handle_idle(loop, ctx),
        "thinking": lambda ctx: handle_thinking(loop, ctx),
        "tool": lambda ctx: handle_tool_calling(loop, ctx),
        "result": lambda ctx: handle_waiting_result(loop, ctx),
        "synthesize": lambda ctx: handle_synthesize(loop, ctx),
        "reply": lambda ctx: handle_direct_reply(loop, ctx),
        "error": lambda ctx: handle_error(loop, ctx),
        "done": lambda ctx: handle_done(loop, ctx),
        "fallback": lambda ctx: handle_fallback(loop, ctx),
    }
