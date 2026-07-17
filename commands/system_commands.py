"""System commands: /exit, /quit, /q, /help, /clear, /status, /setup."""

from __future__ import annotations

from typing import TYPE_CHECKING
from core.constants import t

if TYPE_CHECKING:
    from app import DorinaApp


async def cmd_exit(app: "DorinaApp", cmd: str) -> None:
    """Exit the application."""
    from ui.display import print_info

    print_info(t("exit_message"))
    app.running = False


async def cmd_quit(app: "DorinaApp", cmd: str) -> None:
    """Alias for /exit."""
    await cmd_exit(app, cmd)


async def cmd_q(app: "DorinaApp", cmd: str) -> None:
    """Alias for /exit."""
    await cmd_exit(app, cmd)


async def cmd_help(app: "DorinaApp", cmd: str) -> None:
    """Display the help table."""
    from ui.display import console
    from rich.table import Table
    from rich import box

    tbl = Table(title=t("command_help_title"), border_style="#D4622A", box=box.ROUNDED)
    tbl.add_column(t("command_help_column"), style="#D4622A", width=16)
    tbl.add_column(t("command_help_description"), style="white")
    for cmd_name, desc in [
        ("/new", t("command_help_new")),
        ("/temp", t("command_help_temp")),
        ("/save <name>", t("command_help_save")),
        ("/load <id>", t("command_help_load")),
        ("/sessions", t("command_help_sessions")),
        ("/tasks", t("command_help_tasks")),
        ("/crons", t("command_help_crons")),
        ("/ara <query>", t("command_help_search")),
        ("/skills", t("command_help_skills")),
        ("/tools", t("command_help_tools")),
        ("/model <name>", t("command_help_model")),
        ("/personality", t("command_help_personality")),
        ("/status", t("command_help_status")),
        ("/help", t("command_help_help")),
        ("/clear", t("command_help_clear")),
        ("/exit", t("command_help_exit")),
        ("/export <fmt>", t("command_help_export")),
        ("/dashboard", t("command_help_dashboard")),
    ]:
        tbl.add_row(cmd_name, desc)
    console.print(tbl)


async def cmd_clear(app: "DorinaApp", cmd: str) -> None:
    """Clear the terminal screen."""
    import sys
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()


async def cmd_status(app: "DorinaApp", cmd: str) -> None:
    """Show current status information."""
    from ui.status_bar import status

    status.show()


async def cmd_setup(app: "DorinaApp", cmd: str) -> None:
    """Run the interactive setup wizard."""
    from ui.setup_wizard import run_setup_wizard

    await run_setup_wizard()
