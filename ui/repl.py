"""REPL - prompt_toolkit command line input.
Single PromptSession with bottom toolbar for status bar.

Autocomplete for slash commands: type / -> dropdown list opens.
Filters as you type, Tab to complete.
"""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from core.mode_manager import modes
from core.event_bus import bus
from ui.status_bar import COLOR_PALETTE

# Slash commands - A-Z sorted
SLASH_COMMANDS = sorted([
    "/ara", "/audit", "/clear", "/exit", "/export", "/godmode", "/help", "/load",
    "/model", "/mods", "/new", "/personality", "/q", "/quit",
    "/review", "/save", "/session", "/sessions", "/setup", "/skills", "/status", "/tasks", "/temp", "/tools", "/crons"
])

# Centralized style definitions using COLOR_PALETTE from status_bar
# This creates a dynamic style that changes with the mode
def get_app_style(mode: str) -> Style:
    colors = COLOR_PALETTE.get(mode, COLOR_PALETTE["normal"])
    return Style.from_dict({
        "prompt": f"bold {colors['primary']}",
        "completion-menu": f"bg:#1e1e2e {colors['primary']}",
        "completion-menu.completion": f"bg:#1e1e2e {colors['primary']}",
        "completion-menu.completion.current": f"bg:#45475a {colors['accent']} bold",
        "completion-menu.meta": f"bg:#1e1e2e {colors['dim']}",
        "completion-menu.meta.current": f"bg:#45475a {colors['accent']}",
        "bottom-toolbar": f"fg:{colors['dim']}",
        # Custom styles for status bar fragments, using mode-specific colors
        f"{mode}_primary": f"fg:{colors['primary']} bold",
        f"{mode}_secondary": f"fg:{colors['secondary']}",
        f"{mode}_dim": f"fg:{colors['dim']}",
        f"{mode}_accent": f"fg:{colors['accent']}",
    })


_current_mode_style = get_app_style("normal")

# Prompt symbols for each mode
MODE_PROMPTS = {
    "normal": "> ",
    "godmode": "⚡ > ",
    "audit": "🔍 > ",
    "temp": "💭 > ",
}

def get_prompt() -> str:
    """Return the prompt symbol based on active mode."""
    if modes.is_on('godmode'):
        return MODE_PROMPTS["godmode"]
    elif modes.is_on('audit'):
        return MODE_PROMPTS["audit"]
    elif modes.is_on('temp'):
        return MODE_PROMPTS["temp"]
    return MODE_PROMPTS["normal"]


def set_style(mode: str | None = None):
    """Set REPL style based on mode priority: godmode > audit > temp > normal.

    If mode is provided, toggle that specific mode's style.
    If None (refresh), recalculate from all active states.
    """
    global _current_mode_style
    target_mode = "normal"

    if mode == "godmode" or modes.is_on('godmode'):
        target_mode = "godmode"
    elif mode == "audit" or modes.is_on('audit'):
        target_mode = "audit"
    elif mode == "temp" or modes.is_on('temp'):
        target_mode = "temp"

    _current_mode_style = get_app_style(target_mode)


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
            for style in ["professional", "balanced", "friendly"]:
                if typed.lower() in style.lower():
                    yield Completion(
                        style,
                        start_position=-len(typed),
                        display=style,
                    )
            return

        # Others
        yield from self.nested.get_completions(document, complete_event)

kb = KeyBindings()

@kb.add("c-o")
def _expand_tool(event):
    """ctrl+o: show last tool output."""
    from ui.display import expand_last_tool
    expand_last_tool()
    event.app.invalidate()

@kb.add("c-l")
def _clear_screen(event):
    """ctrl+l: clear terminal screen with mode-aware style."""
    import shutil
    print("\033[2J\033[H", end="", flush=True)
    # Print a mode-styled header after clear
    mode = "normal"
    if modes.is_on('godmode'):
        mode = "godmode"
    elif modes.is_on('audit'):
        mode = "audit"
    elif modes.is_on('temp'):
        mode = "temp"
    colors = COLOR_PALETTE.get(mode, COLOR_PALETTE["normal"])
    term_width = shutil.get_terminal_size().columns
    print(f"\033[38;2;{colors['primary']}m{'─' * term_width}\033[0m")
    event.app.invalidate()

def _setup_mode_listener():
    """Subscribe to mode_change to auto-switch REPL style."""
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


