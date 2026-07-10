"""Goal commands: /goals, /goal cancel <id>, /goal <description>"""

from __future__ import annotations
from typing import TYPE_CHECKING
from core.constants import t

if TYPE_CHECKING:
    from app import DorinaApp


async def cmd_goals(app: "DorinaApp", cmd: str) -> None:
    """List goals and manage them.

    Usage:
        /goals              — list all goals
        /goals running      — list only running goals
        /goal cancel <id>   — cancel a goal
        /goal <desc>        — create and start a new goal
    """
    from orchestrator.goal_manager import goal_manager
    from ui.display import console, print_info, print_error

    args = cmd.split(maxsplit=1)
    sub = args[1].strip() if len(args) > 1 else ""

    # /goals running, /goals all
    if cmd.startswith("/goals"):
        status_filter = ""
        if sub == "running":
            status_filter = "running"
        elif sub:
            print_info(t("goals_usage"))
            return

        goals = goal_manager.list_goals(status_filter)
        if not goals:
            print_info(t("goals_none"))
            return

        from rich.table import Table
        from rich import box
        tbl = Table(border_style="#D4622A", box=box.ROUNDED)
        tbl.add_column("ID", style="cyan")
        tbl.add_column("Goal", style="bold white")
        tbl.add_column("Status", style="magenta")
        tbl.add_column("Duration", style="green")
        tbl.add_column("Started", style="dim")
        for g in goals:
            status_icon = {
                "running": "⟳",
                "completed": "✓",
                "failed": "✗",
                "cancelled": "⊘",
                "pending": "·",
            }.get(g["status"], "?")
            tbl.add_row(
                g["id"],
                g["name"],
                f"{status_icon} {g['status']}",
                g["elapsed"],
                g["created_at"],
            )
        console.print(f"\n[bold #D4622A]# {t('goals_title')}[/bold #D4622A]")
        console.print(tbl)
        return

    # /goal cancel <id>
    if sub.startswith("cancel "):
        goal_id = sub[7:].strip()
        ok = goal_manager.cancel_goal(goal_id)
        if ok:
            print_info(t("goal_cancelled", id=goal_id))
        else:
            print_error(t("goal_not_found", id=goal_id))
        return

    # /goal <description> — create and start
    if sub:
        description = sub
        # Extract a short name from the description
        name = description[:50] + ("..." if len(description) > 50 else "")
        import asyncio

        goal_id = goal_manager.create_goal(name=name, description=description)
        # Detect toolsets from keywords
        toolsets = ["file", "web", "terminal"]
        for kw, ts in [("terminal", "terminal"), ("shell", "terminal"),
                       ("web", "web"), ("internet", "web"), ("research", "web"),
                       ("git", "git"), ("memory", "memory")]:
            if kw in description.lower():
                if ts not in toolsets:
                    toolsets.append(ts)

        print_info(t("goal_starting", name=name))
        result = await goal_manager.start_goal(goal_id, toolsets)
        print_info(result)

        from ui.display import console
        console.print(f"  [dim]{t('goal_monitor')}[/dim]")
    else:
        print_info(t("goal_usage"))


# Alias for /goals (without subcommand)
async def cmd_goal(app: "DorinaApp", cmd: str) -> None:
    """Handle /goal (single goal).

    Usage:
        /goal <id>          — show goal detail
        /goal cancel <id>   — cancel a goal
        /goal <desc>        — create and start a new goal
    """
    from orchestrator.goal_manager import goal_manager
    from ui.display import console, print_info, print_error

    args = cmd.split(maxsplit=2)
    sub = args[1].strip() if len(args) > 1 else ""
    rest = args[2].strip() if len(args) > 2 else ""

    # /goal cancel <id>
    if sub == "cancel" and rest:
        ok = goal_manager.cancel_goal(rest)
        if ok:
            print_info(t("goal_cancelled", id=rest))
        else:
            print_error(t("goal_not_found", id=rest))
        return

    # /goal <id> — detail view
    if sub and len(sub) >= 8 and sub.isalnum():
        goal = goal_manager.get_goal(sub)
        if goal:
            from rich.panel import Panel
            status_icon = {
                "running": "⟳", "completed": "✓",
                "failed": "✗", "cancelled": "⊘", "pending": "·",
            }.get(goal.status, "?")
            detail = (
                f"[bold]ID:[/bold] {goal.id}\n"
                f"[bold]Name:[/bold] {goal.name}\n"
                f"[bold]Status:[/bold] {status_icon} {goal.status}\n"
                f"[bold]Duration:[/bold] {goal.elapsed}\n"
                f"[bold]Turns:[/bold] {goal.turn_count}\n"
            )
            if goal.result:
                # Truncate very long results
                res = goal.result[:800]
                if len(goal.result) > 800:
                    res += "..."
                detail += f"\n[bold]Result:[/bold]\n{res}"
            if goal.error:
                detail += f"\n[bold red]Error:[/bold red]\n{goal.error}"
            console.print(Panel(detail, border_style="#D4622A",
                                title=f"Goal: {goal.short_id}"))
            return

    # Fallback: list all goals
    await cmd_goals(app, cmd)
