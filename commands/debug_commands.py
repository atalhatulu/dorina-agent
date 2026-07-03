"""Debug & transparency commands: /debug, /trace."""
from __future__ import annotations

from typing import TYPE_CHECKING
from core.constants import t

if TYPE_CHECKING:
    from app import DorinaApp

from core.tokenizer import count_tokens, count_messages_tokens


async def cmd_debug(app: "DorinaApp", cmd: str) -> None:
    """Show full debug info — tools, skills, tokens, state."""
    from ui.display import console
    from rich.table import Table
    from rich import box
    from rich.panel import Panel

    tbl = Table(border_style="#D4622A", box=box.ROUNDED)
    tbl.add_column(t("debug_field"), style="bold #D4622A")
    tbl.add_column(t("debug_value"), style="white")

    # Tools
    try:
        from tools.registry import registry
        all_tools = registry.list()
        tbl.add_row(t("debug_tools_total"), str(len(all_tools)))
    except (ImportError, AttributeError):
        tbl.add_row(t("debug_tools_total"), "N/A")

    try:
        from tools.toolset import get_active_toolsets
        active = get_active_toolsets()
        tbl.add_row(t("debug_toolset_active"), f"{len(active)}: {', '.join(sorted(active))}")
    except (ImportError, AttributeError):
        pass

    # Session
    try:
        from orchestrator.experimental_loop import loop_v2 as loop
        msg_count = len(loop.context.get_messages())
        tbl.add_row(t("debug_messages_context"), str(msg_count))
        tbl.add_row(t("debug_turn"), str(getattr(loop, 'turn', '?')))
    except (ImportError, AttributeError):
        pass

    # Skills
    try:
        from skills.manager import skills
        all_sk = skills.list_skills()
        tbl.add_row(t("debug_skills_total"), str(len(all_sk)))
    except (ImportError, AttributeError):
        pass

    try:
        from orchestrator.experimental_loop import loop_v2 as loop
        active = getattr(loop, '_active_skills', None) or []
        tbl.add_row(t("debug_skills_active"), str(len(active)))
        if active:
            names = ", ".join(s['name'] for s in active)
            tbl.add_row(t("debug_skill_names"), names[:80])
    except (ImportError, AttributeError):
        pass

    # Injected prompt size
    enriched = None
    try:
        from orchestrator.experimental_loop import loop_v2 as loop
        enriched = getattr(loop, '_enriched_system_prompt', None)
        if enriched:
            tbl.add_row(t("debug_system_prompt_chars"), str(len(enriched)))
            tbl.add_row(t("debug_system_prompt_tokens"), str(count_tokens(enriched)))
    except (ImportError, AttributeError):
        pass

    # Token usage
    try:
        from ui.status_bar import status
        tbl.add_row(t("debug_tokens_in"), f"{status.tokens_in:,}")
        tbl.add_row(t("debug_tokens_out"), f"{status.tokens_out:,}")
        tbl.add_row(t("debug_cost"), f"${status.cost:.6f}")
    except (ImportError, AttributeError):
        pass

    # Godmode
    try:
        from soul.personality import GODMODE, AUDIT_MODE
        if GODMODE:
            tbl.add_row(t("debug_godmode"), f"⚡ {t('debug_godmode_active')}", style="bold red")
        if AUDIT_MODE:
            tbl.add_row(t("debug_audit"), f"🔍 {t('debug_audit_active')}", style="bold #E06C75")
    except (ImportError, AttributeError):
        pass

    # Model
    try:
        from core.config import settings
        tbl.add_row(t("debug_model"), f"{settings.model.provider}/{settings.model.default.split('/')[-1]}")
    except (ImportError, AttributeError):
        pass

    # Token budget estimate
    try:
        from orchestrator.experimental_loop import loop_v2 as loop
        msg_tokens = count_messages_tokens(loop.context.get_messages())
        from tools.toolset import get_active_schemas
        schemas = get_active_schemas()
        n_tools = len(schemas)
        schema_tokens = n_tools * 250
        sys_tokens = count_tokens(enriched or "")
        total_est = sys_tokens + msg_tokens + schema_tokens
        tbl.add_row(t("debug_estimated_total_tokens"), str(total_est))
        tbl.add_row(t("debug_system_prompt_part"), str(sys_tokens))
        tbl.add_row(t("debug_conversation_history"), str(msg_tokens))
        tbl.add_row(t("debug_tool_schemas", count=n_tools, per_tool=250), f"{schema_tokens}")
    except (ImportError, AttributeError):
        pass

    console.print(Panel(tbl, title="🔍 Dorina Debug", border_style="#D4622A"))


async def cmd_trace(app: "DorinaApp", cmd: str) -> None:
    """Toggle trace mode — log every tool call with full params."""
    from ui.display import console
    console.print(f"[dim]{t('trace_not_implemented')}[/dim]")
