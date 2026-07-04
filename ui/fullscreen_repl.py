"""Full-screen REPL — fixed bottom zone (separator + status + input).

Uses prompt_toolkit Application with full_screen=True (alternate screen buffer).
Conversation output is part of the Layout — a scrollable Window above the
fixed bottom bar. Rich output is captured as ANSI and appended to the
conversation fragment list.

Layout::

    ┌─────────────────────────────────────────┐
    │  Conversation output (scrollable)        │  ← Window w/ FormattedTextControl
    │  ● ReadFile(/etc/hosts)                  │     (takes remaining space)
    │  → /etc/hosts (1.2 KB)                   │
    │  **Merhaba!** Size nasıl...              │
    ├─────────────────────────────────────────┤
    │ ──────────────────────────────────────  │  ← Separator (1 line)
    │  ⟳ Thinking  DeepSeek  13%  27s  turn 3 │  ← Status bar (1 line)
    │ > merhaba                                │  ← Input prompt (1 line)
    └─────────────────────────────────────────┘
"""

from __future__ import annotations
import asyncio
import shutil

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl, BufferControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.formatted_text.base import to_formatted_text

from core.constants import DEFAULT_DATA_DIR, t
from core.mode_manager import modes
from ui.status_bar import status, COLOR_PALETTE
from ui.repl import (
    DorinaCompleter, get_app_style, get_prompt, MODE_PROMPTS,
    _setup_mode_listener,
)

HISTORY_FILE = DEFAULT_DATA_DIR / "history.txt"


class FullScreenREPL:
    """Full-screen prompt_toolkit Application with fixed bottom bar.

    The bottom zone (separator + status bar + input prompt) is rendered
    by the prompt_toolkit Layout and stays fixed at the terminal bottom.
    Conversation output is rendered in a scrollable Window above the
    bottom zone, using a dynamically-updated list of (style, text) fragments.
    """

    def __init__(self, dorina_app):
        self.dorina_app = dorina_app
        self.application: Application | None = None
        self._processing = False
        self._input_buffer: Buffer | None = None
        self._stream_carry = ""  # leftover ANSI from streaming (no trailing newline)

        # Conversation output — fragments for the scrollable window
        self._conv_fragments: list[tuple[str, str]] = []
        self._conv_window: Window | None = None  # set after _create_application

    # ── Public API ────────────────────────────────────────────────────

    async def run(self):
        """Start the full-screen REPL and block until exit."""
        import ui.display as display
        display._fullscreen_app = self

        self._input_buffer = Buffer(
            completer=DorinaCompleter(self._build_nested_completer()),
            history=FileHistory(str(HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
        )
        self.application = self._create_application()

        _setup_mode_listener()

        await self.application.run_async()

        display._fullscreen_app = None

    def _append_ansi(self, ansi: str):
        """Parse an ANSI string and append its fragments to the conversation."""
        if not ansi:
            return
        try:
            for style, text in to_formatted_text(ANSI(ansi)):
                self._conv_fragments.append((style, text))
        except Exception:
            # fallback: treat as plain text
            self._conv_fragments.append(("", ansi))

    def print_output(self, ansi: str):
        """Append ANSI-escaped text to the conversation output window.

        Accepts a plain string (may contain ANSI escape sequences for colour).
        When the text ends without a trailing newline it is carried over so
        the next chunk continues on the same line (streaming support).
        All lines are separated by ``("", "\\n")`` fragments.
        """
        if not self.application or not self.application.is_running:
            return

        if not ansi:
            return

        # Prepend any carried-over content from the previous streaming chunk.
        carry = self._stream_carry
        self._stream_carry = ""

        text = carry + ansi

        # If the chunk itself does not end with a newline, hold it back
        # until a newline arrives (or a flush).
        if not text.endswith("\n"):
            self._stream_carry = text
            self._invalidate_conv()
            return

        lines = text.rstrip("\n").split("\n")
        for i, line in enumerate(lines):
            self._append_ansi(line)
            # Always add a newline after each line in the chunk
            # (the original text ended with \n, so we know a newline is wanted)
            self._conv_fragments.append(("", "\n"))
        self._invalidate_conv()

    def flush_stream(self):
        """Flush any pending streaming content."""
        if self._stream_carry:
            self._append_ansi(self._stream_carry)
            self._stream_carry = ""
            self._invalidate_conv()

    def clear_conversation(self):
        """Clear all conversation output."""
        self._conv_fragments.clear()
        self._invalidate_conv()

    def _invalidate_conv(self):
        """Force the conversation window to re-render and scroll to bottom."""
        if self._conv_window is not None:
            self._conv_window.vertical_scroll = 10**9  # scroll to bottom
        if self.application:
            self.application.invalidate()

    # ── Layout ────────────────────────────────────────────────────────

    def _get_conv_fragments(self) -> list[tuple[str, str]]:
        """Return the accumulated conversation fragments."""
        return self._conv_fragments

    def _create_application(self) -> Application:
        """Build the prompt_toolkit Application."""
        kb = self._build_key_bindings()

        self._conv_window = Window(
            content=FormattedTextControl(self._get_conv_fragments),
            wrap_lines=True,
            style="",
        )

        layout = Layout(
            HSplit([
                self._conv_window,                          # scrollable output
                Window(height=1, char="─", style="class:separator"),
                Window(
                    content=FormattedTextControl(self._get_status_fragments),
                    height=1,
                    style="",
                ),
                Window(
                    content=BufferControl(buffer=self._input_buffer),
                    height=1,
                    get_line_prefix=_line_prefix,
                ),
            ])
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            style=get_app_style("normal"),
            mouse_support=False,
        )

    # ── Status bar fragments ──────────────────────────────────────────

    def _get_status_fragments(self) -> list[tuple[str, str]]:
        """Return formatted-text fragments for the status bar window."""
        return status.get_toolbar_tokens()

    # ── Key bindings ──────────────────────────────────────────────────

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("enter")
        def _submit(event):
            if self._processing:
                return
            text = self._input_buffer.text.strip()
            if not text:
                return
            self._input_buffer.reset()

            if text.lower() in ("/exit", "/quit"):
                event.app.exit()
                return

            self._processing = True
            event.app.invalidate()
            asyncio.create_task(self._process_input(text))

        @kb.add("c-c")
        def _cancel_or_stop(event):
            if self._processing:
                self._processing = False
                event.app.invalidate()
            else:
                from ui.display import console
                console.print()

        @kb.add("c-d")
        def _exit_app(event):
            event.app.exit()

        @kb.add("c-l")
        def _clear(event):
            """Clear the conversation output area."""
            self.clear_conversation()
            event.app.invalidate()

        @kb.add("c-o")
        def _expand_tool(event):
            """Expand last tool output."""
            from ui.display import expand_last_tool
            expand_last_tool()
            event.app.invalidate()

        return kb

    # ── Input processing ──────────────────────────────────────────────

    async def _process_input(self, text: str):
        """Handle one submitted line — command or AI query."""
        try:
            if text.startswith("/"):
                await self.dorina_app._handle_command(text)
                self._processing = False
                if self.application:
                    self.application.invalidate()
                return

            from ui import display
            from ui.status_bar import status
            from orchestrator.experimental_loop import loop_v2 as loop
            import sys
            import termios

            display.print_divider()
            display.print_user(text)
            status.set_status("Thinking")

            # Disable local echo + canonical mode while AI processes
            fd = sys.stdin.fileno()
            old_attr = termios.tcgetattr(fd)
            try:
                new_attr = termios.tcgetattr(fd)
                new_attr[3] = new_attr[3] & ~termios.ECHO & ~termios.ICANON
                termios.tcsetattr(fd, termios.TCSANOW, new_attr)

                response = await loop.process(text)
            except (KeyboardInterrupt, asyncio.CancelledError):
                from ui.display import console as _ui_console, flush_stream as _fs
                _fs()
                _ui_console.print(f"\n[dim]{t('info_cancelled')} (Ctrl+C)[/dim]")
                msgs = loop.context.messages
                cleaned = []
                for m in msgs:
                    if m.get("role") == "assistant" and m.get("tool_calls") and not m.get("content"):
                        continue
                    if m.get("role") == "system" and "Ctrl+C" in (m.get("content") or ""):
                        continue
                    cleaned.append(m)
                while cleaned and cleaned[-1].get("role") == "tool":
                    cleaned.pop()
                while cleaned and cleaned[-1].get("role") == "user" and "Ctrl+C" in (cleaned[-1].get("content", "") or ""):
                    cleaned.pop()
                loop.context.messages = cleaned
                self._processing = False
                if self.application:
                    self.application.invalidate()
                return
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
                termios.tcflush(fd, termios.TCIFLUSH)

            self.flush_stream()

            if not getattr(loop, "_streamed_this_turn", False):
                display.print_assistant(response)

            status.end_turn()
            display.print_divider()

            # Auto-save
            from core.config import settings
            if (
                settings.session.auto_save
                and loop.context.get_messages()
                and not loop._temp_mode
            ):
                from session.manager import manager
                manager.save(
                    loop.context.get_messages(),
                    summary=response[:200] if response else "",
                )

        except Exception as e:
            from ui.display import console
            console.print(f"[red]Error: {e}[/red]")
        finally:
            self._processing = False
            if self.application:
                self.application.invalidate()

    # ── Helpers ───────────────────────────────────────────────────────

    def _build_nested_completer(self):
        """Build the nested completer dictionary for DorinaCompleter."""
        from prompt_toolkit.completion import NestedCompleter
        from providers.keys import PROVIDERS

        model_completions = {}
        for provider, info in PROVIDERS.items():
            for model in info.get("models", []):
                model_completions[f"{provider}/{model}"] = None

        return NestedCompleter.from_nested_dict({
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
                "balanced": None,
                "friendly": None,
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


# ── Module-level helpers ──────────────────────────────────────────────

def _line_prefix(lineno: int, wrapped: bool) -> list[tuple[str, str]]:
    """Prompt symbol shown before the input text."""
    if lineno == 0 and not wrapped:
        mode = _active_mode_str()
        return [(f"class:{mode}_primary", MODE_PROMPTS.get(mode, MODE_PROMPTS["normal"]))]
    return []


def _active_mode_str() -> str:
    """Return short mode string for colour lookup."""
    if modes.is_on("godmode"):
        return "godmode"
    elif modes.is_on("audit"):
        return "audit"
    elif modes.is_on("temp"):
        return "temp"
    return "normal"
