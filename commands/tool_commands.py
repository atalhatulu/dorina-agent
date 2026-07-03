"""Tool & task commands: /tools, /tasks, /crons, /verify, /review, /skills."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from core.constants import t

if TYPE_CHECKING:
    from app import DorinaApp


async def cmd_tools(app: "DorinaApp", cmd: str) -> None:
    """List all registered tools."""
    from tools.registry import registry
    from ui.display import console, print_info

    print_info(t("tools_registered", count=registry.count()))
    for t in registry.list():
        console.print(f"  [cyan]{t.name}[/cyan] [{t.toolset}] — {t.description}")


async def cmd_tasks(app: "DorinaApp", cmd: str) -> None:
    """List background tasks (auto-clears failed ones)."""
    from bg_tools.task_manager import task_manager
    from ui.display import print_table as _pt_tasks, print_info

    task_manager.clear_failed()  # auto-clear failed tasks
    tasks = task_manager.list_tasks()
    if tasks:
        rows = [[t.id, t.name, t.status, t.elapsed] for t in tasks]
        _pt_tasks(t("tasks_title"), ["ID", "Task", "Status", "Duration"], rows)
    else:
        print_info(t("tasks_none"))


async def cmd_crons(app: "DorinaApp", cmd: str) -> None:
    """List scheduled cron jobs."""
    from ui.display import console
    from rich.table import Table
    from rich import box
    from cron.scheduler import cron

    jobs = cron.list_jobs()

    if not jobs:
        console.print(f"  [dim]{t('crons_none')}[/dim]")
    else:
        tbl = Table(title=t("crons_title"), border_style="#D4622A", box=box.ROUNDED)
        tbl.add_column("ID", style="cyan")
        tbl.add_column("Task Name", style="bold white")
        tbl.add_column("Schedule", style="magenta")
        tbl.add_column("Next Run", style="green")

        for j in jobs:
            tbl.add_row(j.id[:8], j.name, j.schedule, str(j.next_run or t("crons_next_unknown")))

        console.print(tbl)


async def cmd_verify(app: "DorinaApp", cmd: str) -> None:
    """Verify tool(s)::

        /verify           # all tools
        /verify --list    # list cached verification statuses
        /verify --reset   # clear verification cache
        /verify <name>    # verify a single tool
    """
    from ui.display import console, print_success, print_info

    _raw = cmd[8:].strip()
    from tools.tool_verify import tool_verify_tool

    if _raw == "--list":
        result = tool_verify_tool(tool_name="--list")
        console.print(f"\n[bold #D4622A]# {t('verify_title')}[/bold #D4622A]")
        console.print(result)

    elif _raw == "--reset":
        result = tool_verify_tool(tool_name="--reset")
        data = json.loads(result) if isinstance(result, str) and result.startswith("{") else result
        print_success(data.get("message", t("verify_cache_cleared")))

    elif _raw:
        # Single tool verify
        console.print(f"\n[bold #D4622A]# Verifying: {_raw}[/bold #D4622A]")
        result = tool_verify_tool(tool_name=_raw)
        data = json.loads(result) if isinstance(result, str) and result.startswith("{") else result
        if isinstance(data, dict):
            s = data.get("status", "?")
            msg = data.get("message", "")
            console.print(f"  {t('verify_status')} {s}")
            console.print(f"  {t('verify_message')} {msg}")
            if data.get("result_preview"):
                console.print(f"  {t('verify_output')} {data['result_preview'][:200]}")
        else:
            console.print(result)

    else:
        # Verify all
        console.print(f"\n[bold #D4622A]# {t('verify_verifying_all')}[/bold #D4622A]")
        result = tool_verify_tool()
        data = json.loads(result) if isinstance(result, str) else result
        if isinstance(data, dict):
            for r in data.get("results", []):
                icon = (
                    "✅"
                    if r.get("status") == "✅"
                    else ("⏭️" if r.get("status") == "⏭️" else "❌")
                )
                console.print(f"  {icon} {r['tool']:<15} {r.get('message', '')[:50]}")
            console.print(f"\n  {data.get('summary', '')}")
        else:
            console.print(result)


async def cmd_review(app: "DorinaApp", cmd: str) -> None:
    """Trigger a code review of recent tool outputs."""
    from orchestrator.experimental_loop import loop_v2 as loop
    from ui.display import print_info, print_assistant

    print_info(t("review_starting"))
    tool_outputs = []
    for m in loop.context.get_messages()[-20:]:
        if m.get("role") == "tool":
            content = str(m.get("content", ""))
            name = m.get("name", "")
            if len(content) > 50:
                tool_outputs.append(f"=== Tool: {name} ===\n{content[:1000]}")
    print_assistant(t("review_note"))


async def cmd_skills(app: "DorinaApp", cmd: str) -> None:
    """List all loaded skills."""
    from skills.manager import skills
    from ui.display import print_table, print_info

    skill_list = skills.list_skills()
    if skill_list:
        rows = [
            [s["name"], s.get("description", ""), str(s.get("use_count", 0))]
            for s in skill_list
        ]
        print_table(t("skills_title"), ["Name", "Description", "Uses"], rows)
    else:
        print_info(t("skills_none"))
