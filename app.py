"""Dorina App — Main application class for CLI REPL and single-query execution."""

from __future__ import annotations
import asyncio
import sys
from typing import Optional

from core.logger import log, console
from core.constants import NAME, VERSION
from session.manager import manager as session_manager
from orchestrator.experimental_loop import loop_v2 as loop
from ui.banner import show_banner
from ui.display import print_info, print_error


class DorinaApp:
    """Main application lifecycle and command loop controller."""

    def __init__(self):
        self.running: bool = True
        self.session_id: Optional[str] = None

    async def startup(self):
        """Startup tasks: session init, banner display."""
        show_banner()
        # Initialize or restore session
        if not session_manager.current_id:
            self.session_id = session_manager.create(title="CLI Session")
        else:
            self.session_id = session_manager.current_id

    async def run_single_query(self, query: str):
        """Execute a single query and exit."""
        if not query:
            return
        log.info(f"Single query execution: {query}")
        result = await loop.run(query)
        if result and isinstance(result, str):
            print_info(result)

    async def run_interactive(self):
        """Run interactive REPL loop."""
        from ui.repl import get_prompt

        print_info(f"Welcome to {NAME} v{VERSION}. Type /help for commands, /exit to quit.")

        while self.running:
            try:
                try:
                    from prompt_toolkit import PromptSession
                    from prompt_toolkit.history import InMemoryHistory
                    if not hasattr(self, "_prompt_session"):
                        self._prompt_session = PromptSession(history=InMemoryHistory())
                    user_input = await self._prompt_session.prompt_async(get_prompt())
                except (ImportError, Exception):
                    user_input = input(get_prompt())

                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.startswith("/"):
                    await self._dispatch_slash_command(user_input)
                else:
                    result = await loop.run(user_input)
                    if result and isinstance(result, str):
                        print_info(result)

            except (KeyboardInterrupt, EOFError):
                print_info("\nGoodbye!")
                self.running = False
                break
            except Exception as exc:
                print_error(f"Error: {exc}")

    async def _dispatch_slash_command(self, cmd_str: str):
        """Dispatch slash commands (e.g. /exit, /help, /model)."""
        cmd_parts = cmd_str.split()
        command_name = cmd_parts[0].lower()

        try:
            if command_name in ("/exit", "/quit", "/q"):
                from commands.system_commands import cmd_exit
                await cmd_exit(self, cmd_str)
            elif command_name == "/help":
                from commands.system_commands import cmd_help
                await cmd_help(self, cmd_str)
            elif command_name == "/clear":
                from commands.system_commands import cmd_clear
                await cmd_clear(self, cmd_str)
            elif command_name == "/status":
                from commands.system_commands import cmd_status
                await cmd_status(self, cmd_str)
            elif command_name == "/setup":
                from commands.system_commands import cmd_setup
                await cmd_setup(self, cmd_str)
            elif command_name in ("/new", "/sessions", "/session", "/export", "/save", "/load"):
                from commands.session_commands import (
                    cmd_new, cmd_sessions, cmd_session, cmd_export, cmd_save, cmd_load
                )
                if command_name == "/new":
                    await cmd_new(self, cmd_str)
                elif command_name == "/sessions":
                    await cmd_sessions(self, cmd_str)
                elif command_name == "/session":
                    await cmd_session(self, cmd_str)
                elif command_name == "/export":
                    await cmd_export(self, cmd_str)
                elif command_name == "/save":
                    await cmd_save(self, cmd_str)
                elif command_name == "/load":
                    await cmd_load(self, cmd_str)
            elif command_name in ("/model", "/godmode", "/audit", "/auto", "/mods", "/speed", "/budget"):
                from commands.config_commands import (
                    cmd_model, cmd_godmode, cmd_audit, cmd_auto, cmd_mods, cmd_speed, cmd_budget
                )
                if command_name == "/model":
                    await cmd_model(self, cmd_str)
                elif command_name == "/godmode":
                    await cmd_godmode(self, cmd_str)
                elif command_name == "/audit":
                    await cmd_audit(self, cmd_str)
                elif command_name == "/auto":
                    await cmd_auto(self, cmd_str)
                elif command_name == "/mods":
                    await cmd_mods(self, cmd_str)
                elif command_name == "/speed":
                    await cmd_speed(self, cmd_str)
                elif command_name == "/budget":
                    await cmd_budget(self, cmd_str)
            elif command_name in ("/goals", "/goal"):
                from commands.goal_commands import cmd_goals, cmd_goal
                if command_name == "/goals":
                    await cmd_goals(self, cmd_str)
                elif command_name == "/goal":
                    await cmd_goal(self, cmd_str)
            elif command_name in ("/tools", "/tasks", "/crons", "/skills"):
                from commands.tool_commands import cmd_tools, cmd_tasks, cmd_crons, cmd_skills
                if command_name == "/tools":
                    await cmd_tools(self, cmd_str)
                elif command_name == "/tasks":
                    await cmd_tasks(self, cmd_str)
                elif command_name == "/crons":
                    await cmd_crons(self, cmd_str)
                elif command_name == "/skills":
                    await cmd_skills(self, cmd_str)
            else:
                print_error(f"Unknown command: {command_name}. Type /help for available commands.")
        except Exception as exc:
            print_error(f"Command error [{command_name}]: {exc}")
