"""Debug & transparency commands: /debug, /trace."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DorinaApp


async def cmd_debug(app: "DorinaApp", cmd: str) -> None:
    """Show full debug info — tools, skills, tokens, state."""
    from ui.display import console
    from rich.table import Table
    from rich import box
    from rich.panel import Panel

    tbl = Table(border_style="#D4622A", box=box.ROUNDED)
    tbl.add_column("Alan", style="bold #D4622A")
    tbl.add_column("Değer", style="white")

    # Tools
    try:
        from tools.registry import registry
        all_tools = registry.list()
        tbl.add_row("Tool (toplam)", str(len(all_tools)))
    except Exception:
        tbl.add_row("Tool (toplam)", "N/A")

    try:
        from tools.selector import selector as _sel
        tbl.add_row("Tool Selector indeksli", str(getattr(_sel, '_total_tools', '?')))
    except Exception:
        pass

    # Session
    try:
        from orchestrator.agent_loop import loop
        msg_count = len(loop.context.get_messages())
        tbl.add_row("Mesaj (context)", str(msg_count))
        tbl.add_row("Tur", str(getattr(loop, 'turn', '?')))
    except Exception:
        pass

    # Skills
    try:
        from skills.manager import skills
        all_sk = skills.list_skills()
        tbl.add_row("Skill (toplam)", str(len(all_sk)))
    except Exception:
        pass

    try:
        from orchestrator.agent_loop import loop
        active = getattr(loop, '_active_skills', None) or []
        tbl.add_row("Skill (aktif)", str(len(active)))
        if active:
            names = ", ".join(s['name'] for s in active)
            tbl.add_row("Skill isimleri", names[:80])
    except Exception:
        pass

    # Injected prompt size
    enriched = None
    try:
        from orchestrator.agent_loop import loop
        enriched = getattr(loop, '_enriched_system_prompt', None)
        if enriched:
            tbl.add_row("Sistem prompt (karakter)", str(len(enriched)))
            tbl.add_row("Sistem prompt (~token)", str(len(enriched) // 4))
    except Exception:
        pass

    # Token usage
    try:
        from ui.status_bar import status
        tbl.add_row("Token in", f"{status.tokens_in:,}")
        tbl.add_row("Token out", f"{status.tokens_out:,}")
        tbl.add_row("Maliyet", f"${status.cost:.6f}")
    except Exception:
        pass

    # Godmode
    try:
        from soul.personality import GODMODE, AUDIT_MODE
        if GODMODE:
            tbl.add_row("Godmode", "⚡ AKTİF", style="bold red")
        if AUDIT_MODE:
            tbl.add_row("Audit", "🔍 ACIK", style="bold #E06C75")
    except Exception:
        pass

    # Model
    try:
        from core.config import settings
        tbl.add_row("Model", f"{settings.model.provider}/{settings.model.default.split('/')[-1]}")
    except Exception:
        pass

    # Token budget estimate
    try:
        from orchestrator.agent_loop import loop
        msg_tokens = sum(len(str(m.get("content", ""))) for m in loop.context.get_messages()) // 4
        from tools.selector import selector as _sel
        selected = getattr(_sel, '_cache', {}).get('tools', [])
        schema_tokens = len(selected) * 250
        sys_tokens = len(enriched or "") // 4
        total_est = sys_tokens + msg_tokens + schema_tokens
        tbl.add_row("Tahmini toplam token", str(total_est))
        tbl.add_row("  - Sistem prompt", str(sys_tokens))
        tbl.add_row("  - Konuşma geçmişi", str(msg_tokens))
        tbl.add_row("  - Tool şemaları", f"{schema_tokens} ({len(selected)} tool x ~250)")
    except Exception:
        pass

    console.print(Panel(tbl, title="🔍 Dorina Debug", border_style="#D4622A"))


async def cmd_trace(app: "DorinaApp", cmd: str) -> None:
    """Toggle trace mode — log every tool call with full params."""
    from ui.display import console
    console.print("[dim]Trace modu henuz implemente edilmedi. /debug kullanin.[/dim]")
