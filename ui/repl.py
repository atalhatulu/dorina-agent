"""REPL - prompt_toolkit ile komut satırı girdisi.
Single PromptSession with bottom toolbar for status bar.

Slash komutları için autocomplete: / yaz → dropdown liste açılır.
Yazdıkça daralır, Tab ile tamamlanır.
"""

from __future__ import annotations
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter, NestedCompleter, Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings

from core.constants import DEFAULT_DATA_DIR
from core.mode_manager import modes
from core.event_bus import bus
HISTORY_FILE = DEFAULT_DATA_DIR / "history.txt"

# Slash commands - A-Z sorted
SLASH_COMMANDS = sorted([
    "/ara", "/audit", "/clear", "/exit", "/export", "/godmode", "/help", "/load",
    "/model", "/mods", "/new", "/personality", "/q", "/quit",
    "/review", "/save", "/session", "/sessions", "/setup", "/skills", "/status", "/tasks", "/temp", "/tools", "/crons"
])

NORMAL_STYLE = Style.from_dict({
    "prompt": "bold #D4622A",
    "completion-menu": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #D4622A bold",
    "completion-menu.meta": "bg:#1e1e2e #6c7086",
    "completion-menu.meta.current": "bg:#45475a #D4622A",
    "bottom-toolbar": "bg:#1a1a1a #5C6370",
    "godmode": "bg:#3d0000 bold #ff3333",
    "godmode_dim": "bg:#3d0000 #cc2222",
    "audit": "bold #E06C75",
    "temp": "bold #6C7086",
    "temp_dim": "#585B70",
    "orange": "bold #E06C75",
    "main": "#ABB2BF",
    "dim": "#5C6370",
    "green": "#98C379",
})

GODMODE_STYLE = Style.from_dict({
    "prompt": "bold #ff3333",
    "completion-menu": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #ff3333 bold",
    "completion-menu.meta": "bg:#1e1e2e #6c7086",
    "completion-menu.meta.current": "bg:#45475a #ff3333",
    "bottom-toolbar": "bg:#3d0000 #cc2222",
    "godmode": "bg:#3d0000 bold #ff3333",
    "godmode_dim": "bg:#3d0000 #cc2222",
    "audit": "bold #E06C75",
    "temp": "bold #6C7086",
    "temp_dim": "#585B70",
    "orange": "bold #ff3333",
    "main": "#ffaaaa",
    "dim": "#cc6666",
    "green": "#ff6666",
})

AUDIT_STYLE = Style.from_dict({
    "prompt": "bold #E06C75",
    "completion-menu": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #E06C75 bold",
    "completion-menu.meta": "bg:#1e1e2e #6c7086",
    "completion-menu.meta.current": "bg:#45475a #E06C75",
    "bottom-toolbar": "bg:#1a1a1a #5C6370",
    "godmode": "bg:#3d0000 bold #ff3333",
    "godmode_dim": "bg:#3d0000 #cc2222",
    "audit": "bold #E06C75",
    "temp": "bold #6C7086",
    "temp_dim": "#585B70",
    "orange": "bold #D4622A",
    "main": "#ABB2BF",
    "dim": "#5C6370",
    "green": "#98C379",
})

TEMP_STYLE = Style.from_dict({
    "prompt": "bold #6C7086",
    "completion-menu": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #6C7086 bold",
    "completion-menu.meta": "bg:#1e1e2e #6c7086",
    "completion-menu.meta.current": "bg:#45475a #6C7086",
    "bottom-toolbar": "bg:#1a1a1a #585B70",
    "godmode": "bg:#3d0000 bold #ff3333",
    "godmode_dim": "bg:#3d0000 #cc2222",
    "audit": "bold #E06C75",
    "temp": "bold #6C7086",
    "temp_dim": "#585B70",
    "orange": "bold #6C7086",
    "main": "#585B70",
    "dim": "#585B70",
    "green": "#6C7086",
})

STYLE = NORMAL_STYLE


_session: PromptSession | None = None

def set_style(mode: str | bool | None = None):
    """Set REPL style based on mode priority: godmode > audit > temp > normal.
    
    If mode is provided, toggle that specific mode's style.
    If None (refresh), recalculate from all active states.
    """
    global STYLE
    
    # Priority: godmode > audit > temp
    if mode == True or mode == "godmode":
        STYLE = GODMODE_STYLE
    elif mode == "audit":
        STYLE = AUDIT_STYLE
    elif mode == "temp":
        # Only set temp if no higher-priority mode is active
        if modes.is_on('godmode'):
            STYLE = GODMODE_STYLE
        elif modes.is_on('audit'):
            STYLE = AUDIT_STYLE
        else:
            STYLE = TEMP_STYLE
    else:
        # Refresh from actual states
        if modes.is_on('godmode'):
            STYLE = GODMODE_STYLE
        elif modes.is_on('audit'):
            STYLE = AUDIT_STYLE
        elif modes.is_on('temp'):
            STYLE = TEMP_STYLE
        else:
            STYLE = NORMAL_STYLE
    
    if _session:
        _session.app.style = STYLE



class DorinaCompleter(Completer):
    def __init__(self, nested):
        self.nested = nested

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # /model
        if text.strip() == "/model" or text.strip().startswith("/model "):
            from providers.keys import PROVIDERS
            typed = text.strip()[len("/model"):].strip()
            for provider, info in PROVIDERS.items():
                for model in info.get("models", []):
                    full = f"{provider}/{model}"
                    if typed.lower() in full.lower():
                        yield Completion(
                            full,
                            start_position=-len(typed),
                            display=full,
                            display_meta=info.get("url", ""),
                        )
            return

        # /personality
        if text.strip() == "/personality" or text.strip().startswith("/personality "):
            typed = text.strip()[len("/personality"):].strip()
            for style in ["professional", "dengeli", "arkadas"]:
                if typed.lower() in style.lower():
                    yield Completion(
                        style,
                        start_position=-len(typed),
                        display=style,
                    )
            return
        
        # Digerleri
        yield from self.nested.get_completions(document, complete_event)

kb = KeyBindings()

@kb.add("c-o")
def _expand_tool(event):
    """ctrl+o: son tool çıktısını göster."""
    from ui.display import expand_last_tool
    expand_last_tool()
    event.app.invalidate()

def create_session() -> PromptSession:
    """Create single PromptSession with bottom toolbar."""
    global _session

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    from providers.keys import PROVIDERS
    model_completions = {}
    for provider, info in PROVIDERS.items():
        for model in info.get("models", []):
            model_completions[f"{provider}/{model}"] = None

    cmd_completer = NestedCompleter.from_nested_dict({
        "/model": model_completions,
        "/mods": None,
        "/load": None,
        "/ara": None,
        "/audit": None,
        "/clear": None,
        "/exit": None,
        "/export": None,
        "/godmode": None,
        "/help": None,
        "/new": None,
        "/personality": {
            "professional": None,
            "dengeli": None,
            "arkadas": None,
        },
        "/q": None,
        "/quit": None,
        "/review": None,
        "/save": None,
        "/sessions": None,
        "/setup": None,
        "/skills": None,
        "/status": None,
        "/tasks": None,
        "/temp": None,
        "/crons": None,
        "/tools": None,
        "/session": {
            "prune": None,
            "archive": None,
            "size": None,
        },
    })
    from ui.status_bar import status

    _session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=DorinaCompleter(cmd_completer),
        complete_while_typing=True,
        style=STYLE,
        enable_history_search=True,
        bottom_toolbar=status.get_toolbar_tokens,
        refresh_interval=0.5,
        wrap_lines=True,
        key_bindings=kb,
    )
    return _session


async def get_input(session: PromptSession | None = None) -> str:
    """Kullanıcıdan girdi al. TTY yoksa fallback input()."""
    from prompt_toolkit.patch_stdout import patch_stdout

    s = session or _session

    if s is None or not sys.stdin.isatty():
        try:
            return input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    try:
        with patch_stdout():
            # Flush existing keyboard input buffer (so typing during AI response is discarded)
            try:
                import termios
                termios.tcflush(sys.stdin, termios.TCIFLUSH)
            except OSError:
                pass
            
            import asyncio
            async def _watch_notifications():
                try:
                    from bg_tools.task_manager import task_manager
                    from prompt_toolkit import print_formatted_text
                    from prompt_toolkit.formatted_text import FormattedText
                    while True:
                        await asyncio.sleep(0.5)
                        for notif in task_manager.pop_notifications():
                            # Use prompt_toolkit native print to avoid ANSI corruption via patch_stdout
                            # ✓ for success, ✗ for fail, ▶ for start
                            color = "class:orange"
                            if "✓" in notif:
                                color = "class:green"
                            elif "✗" in notif or "⚠" in notif:
                                color = "class:godmode"
                            print_formatted_text(FormattedText([(color, f"  {notif}")]))
                except asyncio.CancelledError:
                    pass

            watcher_task = asyncio.create_task(_watch_notifications())
            try:
                result = await s.prompt_async("> ", style=STYLE)
            finally:
                watcher_task.cancel()
            
            return result.strip()
    except (EOFError, KeyboardInterrupt):
        return "/exit"


def _setup_mode_listener():
    """Subscribe to mode_change to auto-switch REPL style."""
    from core.mode_manager import modes

    def _on_mode_change(**kw):
        if modes.is_on('godmode'):
            set_style('godmode')
        elif modes.is_on('audit'):
            set_style('audit')
        elif modes.is_on('temp'):
            set_style('temp')
        else:
            set_style('')

    bus.subscribe("mode_change", _on_mode_change)


_setup_mode_listener()
