"""Command registry — maps slash-command prefixes to handler functions.

Each handler signature::

    async def handler(app, cmd: str) -> None

Where ``app`` is the ``DorinaApp`` instance and ``cmd`` is the full command string
(e.g. ``/save my-session``).  The handler is responsible for parsing args from it.

Usage in ``main.py``::

    from commands import register_commands
    CMD_REGISTRY = register_commands()

    async def _handle_command(self, command: str):
        prefix = command.lower().split()[0]
        handler = CMD_REGISTRY.get(prefix)
        if handler:
            await handler(self, command)
        else:
            print_info(f"Unknown command: {command}. Type /help.")
"""

from __future__ import annotations
from typing import Callable, Coroutine

# CommandHandler = Callable[[DorinaApp, str], Coroutine] — kept as comment for docs
# DorinaApp import is intentionally avoided here to prevent circular imports.
# Handlers receive (app, cmd) at runtime regardless of static typing.
CommandHandler = Callable[..., Coroutine]


def register_commands() -> dict[str, CommandHandler]:
    """Build the prefix → handler mapping for all slash commands."""
    from commands.session_commands import (
        cmd_new, cmd_temp, cmd_save, cmd_load, cmd_sessions,
        cmd_remove, cmd_clean, cmd_ara, cmd_export, cmd_session,
    )
    from commands.system_commands import (
        cmd_exit, cmd_quit, cmd_q, cmd_help, cmd_clear, cmd_status, cmd_setup,
    )
    from commands.config_commands import (
        cmd_model, cmd_godmode, cmd_audit, cmd_mods, cmd_personality,
        cmd_speed, cmd_budget, cmd_auto,
    )
    from commands.tool_commands import (
        cmd_tools, cmd_tasks, cmd_crons, cmd_verify, cmd_review, cmd_skills,
    )
    from commands.debug_commands import cmd_debug, cmd_trace
    from commands.goal_commands import cmd_goals, cmd_goal

    return {
        "/exit": cmd_exit,
        "/quit": cmd_quit,
        "/q": cmd_q,
        "/new": cmd_new,
        "/temp": cmd_temp,
        "/godmode": cmd_godmode,
        "/audit": cmd_audit,
        "/auto": cmd_auto,
        "/model": cmd_model,
        "/export": cmd_export,
        "/save": cmd_save,
        "/load": cmd_load,
        "/sessions": cmd_sessions,
        "/remove": cmd_remove,
        "/clean": cmd_clean,
        "/ara": cmd_ara,
        "/skills": cmd_skills,
        "/review": cmd_review,
        "/crons": cmd_crons,
        "/tools": cmd_tools,
        "/tasks": cmd_tasks,
        "/session": cmd_session,
        "/verify": cmd_verify,
        "/status": cmd_status,
        "/setup": cmd_setup,
        "/help": cmd_help,
        "/personality": cmd_personality,
        "/mods": cmd_mods,
        "/speed": cmd_speed,
        "/budget": cmd_budget,
        "/clear": cmd_clear,
        "/debug": cmd_debug,
        "/trace": cmd_trace,
        "/goal": cmd_goal,
        "/goals": cmd_goals,
    }
