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
from prompt_toolkit.data_structures import Point

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
        self._cursor_line = 0   # cursor Y for FormattedTextControl — matched to scroll_target to prevent do_scroll from adjusting
        self._scroll_target = 0  # vertical_scroll set via get_vertical_scroll callback (before do_scroll)

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
        Supports real-time streaming: even if the text doesn't end with a newline,
        it is rendered immediately. The next chunk will replace the previous
        incomplete line and continue streaming smoothly.
        """
        if not self.application or not self.application.is_running:
            return

        if not ansi:
            return

        # 1. Roll back the previous incomplete stream carry from the end of fragments
        if self._stream_carry:
            try:
                carry_frags = list(to_formatted_text(ANSI(self._stream_carry)))
                num_to_pop = len(carry_frags)
                if num_to_pop > 0 and len(self._conv_fragments) >= num_to_pop:
                    for _ in range(num_to_pop):
                        self._conv_fragments.pop()
            except Exception:
                if self._conv_fragments:
                    self._conv_fragments.pop()

        # 2. Combine previous carry with new chunk
        text = self._stream_carry + ansi
        self._stream_carry = ""

        # 3. If text doesn't end with a newline, store the last segment as the new carry
        lines = text.split("\n")
        if not text.endswith("\n"):
            self._stream_carry = lines[-1]

        # 4. Append all segments to the conversation fragments list
        for i, line in enumerate(lines):
            if i > 0:
                self._conv_fragments.append(("", "\n"))
            if line:
                self._append_ansi(line)

        self._invalidate_conv(force_scroll_bottom=True)

    def flush_stream(self):
        """Flush any pending streaming content."""
        if self._stream_carry:
            self._append_ansi(self._stream_carry)
            self._stream_carry = ""
            self._invalidate_conv(force_scroll_bottom=True)

    def clear_conversation(self):
        """Clear all conversation output and reset scroll state."""
        self._conv_fragments.clear()
        self._cursor_line = 0
        self._scroll_target = 0
        self._invalidate_conv()

    def _invalidate_conv(self, force_scroll_bottom: bool = False):
        """Force the conversation window to re-render.

        When force_scroll_bottom is set, cursor and scroll are positioned so
        that the last content line is at the bottom of the viewport.
        _scroll_without_linewrapping's do_scroll then keeps both stable:
        scroll and cursor are coordinated so neither check fires.

        Layout height = terminal height - 3 (separator + status + input).
        """
        if force_scroll_bottom:
            line_cnt = self._get_line_count()
            self._cursor_line = max(0, line_cnt - 1)
            # Estimate conversation window height
            conv_height = max(1, shutil.get_terminal_size().lines - 3)
            self._scroll_target = max(0, line_cnt - conv_height)
        if self.application:
            self.application.invalidate()

    def _get_line_count(self) -> int:
        """Count newline-separated lines in the conversation fragments.

        Each ``\\n`` fragment starts a new line.  The count is the number of
        newlines + 1 (there is always at least one line).
        """
        count = 1
        for _, text in self._conv_fragments:
            count += text.count("\n")
        return count

    def _get_cursor_point(self) -> Point:
        """Return the cursor position for the FormattedTextControl.

        Clamped to the last valid content line so that do_scroll in
        _scroll_without_linewrapping can compute a proper scroll target.
        """
        max_line = max(0, self._get_line_count() - 1)
        return Point(x=0, y=min(self._cursor_line, max_line))

    # ── Layout ────────────────────────────────────────────────────────

    def _get_scroll(self, window: object) -> int:
        """Callback for Window.get_vertical_scroll.

        Returns the scroll_target so that _scroll_without_linewrapping starts
        from our desired scroll position.  do_scroll runs afterward and will
        NOT modify the value as long as cursor_line is coordinated.
        """
        return self._scroll_target

    def _get_conv_fragments(self) -> list[tuple[str, str]]:
        """Return the accumulated conversation fragments."""
        return self._conv_fragments

    def _create_application(self) -> Application:
        """Build the prompt_toolkit Application."""
        kb = self._build_key_bindings()

        self._conv_window = Window(
            content=FormattedTextControl(
                self._get_conv_fragments,
                get_cursor_position=self._get_cursor_point,
            ),
            get_vertical_scroll=self._get_scroll,
            wrap_lines=False,
            style="",
            allow_scroll_beyond_bottom=True,
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
            ]),
            focused_element=self._conv_window,
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            style=get_app_style("normal"),
            mouse_support=True,
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

        @kb.add("up")
        def _scroll_up(event):
            self._scroll_target = max(0, self._scroll_target - 1)
            self._cursor_line = self._scroll_target
            event.app.invalidate()

        @kb.add("down")
        def _scroll_down(event):
            self._scroll_target += 1
            self._cursor_line = self._scroll_target
            event.app.invalidate()

        @kb.add("pageup")
        def _page_up(event):
            step = 20
            if self._conv_window is not None and self._conv_window.render_info is not None:
                step = self._conv_window.render_info.window_height
            self._scroll_target = max(0, self._scroll_target - step)
            self._cursor_line = self._scroll_target
            event.app.invalidate()

        @kb.add("pagedown")
        def _page_down(event):
            step = 20
            if self._conv_window is not None and self._conv_window.render_info is not None:
                step = self._conv_window.render_info.window_height
            self._scroll_target += step
            self._cursor_line = self._scroll_target
            event.app.invalidate()

        @kb.add("c-home")
        def _scroll_top(event):
            self._scroll_target = 0
            self._cursor_line = 0
            event.app.invalidate()

        @kb.add("c-end")
        def _scroll_bottom(event):
            line_cnt = self._get_line_count()
            conv_height = max(1, shutil.get_terminal_size().lines - 3)
            self._scroll_target = max(0, line_cnt - conv_height)
            self._cursor_line = max(0, line_cnt - 1)
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

            # Disable local echo + canonical mode while AI processes if stdin is a tty
            is_tty = sys.stdin.isatty()
            if is_tty:
                fd = sys.stdin.fileno()
                old_attr = termios.tcgetattr(fd)
                new_attr = termios.tcgetattr(fd)
                new_attr[3] = new_attr[3] & ~termios.ECHO & ~termios.ICANON
                termios.tcsetattr(fd, termios.TCSANOW, new_attr)

            try:
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
                if is_tty:
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
