"""Terminal UI - #D4622A orange theme, safe with Text.append."""
from __future__ import annotations
from core.constants import t
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from rich import box
import re as _re
import json as _json
import threading as _threading
import time as _time
import io as _io

_RE_FILE_LINE = _re.compile(r'File "([^"]+)", line (\d+)')
_RE_FILE_LINE2 = _re.compile(r'[-\s]+File "([^"]+)", line (\d+)')

from prompt_toolkit.output import create_output
from prompt_toolkit.patch_stdout import patch_stdout as _pt_patch

from core.mode_manager import modes
from core.tokenizer import count_tokens

# ── Full-screen routing ───────────────────────────────────────────────
_fullscreen_app = None  # Set by FullScreenREPL at start, cleared on exit


class _AppAwareConsole:
    """Rich Console that routes output through FullScreenREPL when active.

    In normal (non-fullscreen) mode, delegates to the real Rich Console.
    In fullscreen mode, captures Rich output as ANSI text and sends it
    to the FullScreenREPL instance, which renders it in the output area
    above the fixed bottom zone.
    """

    def __init__(self, real_console: Console):
        self._real = real_console

    def print(self, *args, **kwargs):
        app = _fullscreen_app
        if app is None:
            self._real.print(*args, **kwargs)
            return

        end = kwargs.pop("end", "\n")
        # Capture Rich output to ANSI (no trailing newline)
        buf = _io.StringIO()
        cap = Console(
            file=buf, force_terminal=True, color_system="truecolor",
            width=self._real.width, highlight=False,
        )
        cap.print(*args, **kwargs, end="")
        ansi = buf.getvalue()

        if not ansi and end == "\n":
            # Blank line
            app.print_output("\n")
            return

        if end == "\n":
            app.print_output(ansi + "\n")
        else:
            app.print_output(ansi)

    def __getattr__(self, name):
        return getattr(self._real, name)


# Initial console (will be wrapped by _AppAwareConsole below)
console = Console(highlight=False)


# ── Full-screen helpers ───────────────────────────────────────────────

def _print_raw_ansi(ansi: str):
    """Print pre-rendered ANSI text, routing via fullscreen app if active."""
    if _fullscreen_app:
        _fullscreen_app.print_output(ansi + "\n")
    else:
        console._real.print(ansi, markup=False)


# Wrap console with app-aware version (must be after all class defs above)
console = _AppAwareConsole(console)

_tool_outputs: list[dict] = []

def store_tool_output(name: str, result: str):
    """Store tool output, expandable via ctrl+o."""
    _tool_outputs.append({
        "name": name,
        "result": result,
        "expanded": False,
        "index": len(_tool_outputs),
    })

def expand_last_tool():
    """Print the last tool output to screen."""
    if not _tool_outputs:
        return
    last = _tool_outputs[-1]
    console.print()
    console.print(f"  [dim]── {last['name']} output ──[/dim]")
    lines = last["result"].split("\n")[:50]
    for line in lines:
        console.print(f"  {line}", highlight=False, markup=False)
    if len(last["result"].split("\n")) > 50:
        console.print(f"  [dim]... ({t('tool_output_more_lines', count=len(last['result'].split(chr(10)))-50)})[/dim]")
    console.print()

def clear_tool_outputs():
    """Clear at session start."""
    _tool_outputs.clear()

INDENT = "  "

ORANGE = "#D4622A"
TEXT   = "#F0EAD8"
USER   = "#E08F5A"
DIM    = "#8A8478"
GREEN  = "#6BB05D"

# Mode-aware color overrides
_MODE_ACCENT = {
    "normal": "#D4622A",
    "godmode": "#ff3333",
    "audit": "#E06C75",
    "temp": "#6C7086",
}
_MODE_GREEN = {
    "normal": "#6BB05D",
    "godmode": "#ff6666",
    "audit": "#98C379",
    "temp": "#6C7086",
}


def _active_mode() -> str:
    """Return current mode string."""
    if modes.is_on('godmode'):
        return "godmode"
    elif modes.is_on('audit'):
        return "audit"
    elif modes.is_on('temp'):
        return "temp"
    return "normal"

_stream_started = False

def _safe_str(s: str, max_len: int = 120) -> str:
    return str(s or "").strip()[:max_len]


def print_user(message: str):
    txt = Text()
    txt.append(INDENT + "> ", style=f"bold {USER}")
    txt.append(message, style=f"italic {TEXT}")
    console.print(txt)


def print_assistant(message: str):
    message = _re.sub(r'<[^>]+>.*?</[^>]+>', '', message, flags=_re.DOTALL)
    message = _re.sub(r'\n\s*\n\s*\n+', '\n\n', message).strip()
    if not message:
        return
    console.print()
    width = console.width - 4

    # Render Markdown → ANSI via a capture Console, then route through
    # the app-aware console so fullscreen mode displays it correctly.
    buf = _io.StringIO()
    md_console = Console(
        file=buf, width=width, highlight=False, soft_wrap=False,
        force_terminal=True, color_system="truecolor",
    )
    from rich.padding import Padding
    # Prepend "Dorina : " label before the markdown content
    label = Text("Dorina : ", style=f"bold {ORANGE}")
    md_console.print(label, end="", justify="left")
    padded_md = Padding(Markdown(message), (0, 0, 0, 2))
    md_console.print(padded_md, justify="left")
    rendered = buf.getvalue()
    if rendered:
        _print_raw_ansi(rendered)
    console.print()


def print_assistant_stream(chunk: str):
    global _stream_buffer, _stream_started
    with _stream_lock:
        if not _stream_started and chunk:
            # Add INDENT on first chunk
            _stream_buffer += INDENT + chunk
            _stream_started = True
        else:
            _stream_buffer += chunk

        if (len(_stream_buffer) >= 40
                or _stream_buffer.endswith(("\n", ". ", "! ", "? ", ": ", "; "))):
            console.print(_stream_buffer, end="", highlight=False, markup=False)
            _stream_buffer = ""


_stream_buffer = ""
_stream_lock = _threading.Lock()


def flush_stream():
    global _stream_buffer, _stream_started
    with _stream_lock:
        if _stream_buffer:
            console.print(_stream_buffer, end="", highlight=False, markup=False)
            _stream_buffer = ""
        _stream_started = False  # reset for next response
    # Also flush the fullscreen app's stream carry
    if _fullscreen_app:
        _fullscreen_app.flush_stream()


_current_tool_text = None

def print_tool_start(name: str, args: dict | None = None):
    global _tool_start_time, _current_tool_text
    _tool_start_time = _time.time()

    mode = _active_mode()
    accent = _MODE_ACCENT[mode]
    arg_color = _MODE_GREEN[mode]

    pascal_name = "".join(word.capitalize() for word in name.split("_"))
    arg_str = ""
    if args:
        matched = {k for k in args if k in {"path","code","command","query","question","prompt","message","pattern","text","url"}}
        if matched:
            key = matched.pop()
            val = str(args.get(key, ""))
            val = val.replace("\n", "\\n")
            arg_str = _safe_str(val, 60)

        if not arg_str:
            import json as _json
            try:
                arg_str = _safe_str(_json.dumps(args, ensure_ascii=False), 60)
            except (TypeError, ValueError, OverflowError):
                arg_str = _safe_str(str(args), 60)

    txt = Text()
    txt.append(INDENT)
    txt.append("● ", style=DIM)
    txt.append(f"{pascal_name}", style="bold")
    txt.append(f"({arg_str})", style=arg_color)  # parameters - mode-aware
    # Parameter token estimation
    global _in_tokens
    _in_tokens = 0
    if args:
        _in_tokens = count_tokens(str(args))

    _current_tool_text = txt
    console.print(txt, end="")


def print_tool_done(name: str, result: str):
    store_tool_output(name, result)
    global _tool_start_time, _current_tool_text, _in_tokens
    mode = _active_mode()
    accent = _MODE_ACCENT[mode]
    _duration = f" \n~{max(0.0, _time.time() - _tool_start_time):.1f}s" if _tool_start_time else ""
    _tool_start_time = 0
    # Input/output token estimation
    _out_tokens = count_tokens(result or "")
    _in_str = f"  i: {_in_tokens}" if _in_tokens > 0 else ""
    _out_str = f"  o: {_out_tokens}" if _out_tokens > 0 else ""
    _io = _in_str + _out_str
    _in_tokens = 0
    raw = str(result or "").strip()
    is_multi = "\n" in raw[:200]
    summary = raw[:120]

    try:
        data = _json.loads(result) if result.startswith("{") else {}
        if "error" in data:
            err_msg = _safe_str(data["error"], 100)
            if _current_tool_text:
                console.print(f" →  [italic {ORANGE}]Error: {err_msg}[/italic {ORANGE}]")
                _current_tool_text = None
            else:
                console.print(f"{INDENT}→ [italic {ORANGE}]Error: {err_msg}[/italic {ORANGE}]")
            return
        if "path" in data:
            summary = f"{data['path']} ({data.get('bytes','?')} B)"
        elif "results" in data:
            r = data["results"]
            if r and isinstance(r[0], dict) and "title" in r[0]:
                summary = t("tool_output_count", count=len(r))
            else:
                summary = t("tool_output_count", count=len(r))
        elif "note" in data:
            summary = data["note"][:150]
        elif data.get("success"):
            summary = data.get("message", t("tool_output_success"))
    except (_json.JSONDecodeError, AttributeError, KeyError, TypeError):
        pass

    if is_multi:
        fl = _safe_str(raw.split("\n")[0], 100)
        summary = f"{fl} ({t('tool_output_lines', count=raw.count(chr(10))+1)}, {len(raw)} B)"

    # sudo password prompt: separate line + obvious background color
    _sudo_style = "bold #ffffff on #cc0000"  # white text, red background
    if "sudo" in summary.lower() and "password" in summary.lower():
        _current_tool_text = None
        console.print(f"\n{INDENT}[bold #ffffff on #cc0000] ── [sudo] password requested ── [/]")
        return

    if _current_tool_text:
        line = Text()
        line.append(" →", style=f"bold {accent}")
        line.append(f" {_safe_str(summary, 120)}")
        console.print(line)
        if _duration or _io:
            console.print(f"{INDENT} {_duration.strip()} {_io.strip()}", style="dim")
        _current_tool_text = None
    else:
        line = Text()
        line.append(f"{INDENT}→", style=f"bold {accent}")
        line.append(f" {_safe_str(summary, 120)}")
        console.print(line)
        if _duration or _io:
            console.print(f"{INDENT}{INDENT}{_duration.strip()} {_io.strip()}", style="dim")


def print_tool_error(name: str, error: str):
    mode = _active_mode()
    accent = _MODE_ACCENT[mode]
    raw = str(error or "")
    msg = raw[:120]
    if raw.strip().startswith("{"):
        try:
            p = _json.loads(raw)
            msg = p.get("error", "") or p.get("message", "") or msg
        except (_json.JSONDecodeError, KeyError, TypeError):
            pass
    user_msg = _friendly_error(msg)
    import logging as _logging
    _logging.getLogger("dorina").debug(f"Tool error [{name}]: {raw[:300]}")
    location = _find_error_location(raw)
    txt = Text()
    txt.append(INDENT + "✗ ", style=accent)
    txt.append(user_msg or msg)
    if location:
        txt.append(" ", style="")
        txt.append(location, style=DIM)
    console.print(txt)


def _find_error_location(raw: str) -> str | None:
    m = _RE_FILE_LINE.search(raw)
    if m:
        fname = m.group(1).split("/")[-1]
        return f"{fname}:{m.group(2)}"
    m = _RE_FILE_LINE2.search(raw)
    if m:
        fname = m.group(1).split("/")[-1]
        return f"{fname}:{m.group(2)}"
    return None


def _friendly_error(msg: str) -> str | None:
    msg = msg[:120]
    if "closing tag" in msg and "doesn't match" in msg:
        return t("error_friendly_ui_component")
    if "MarkupError" in msg:
        return t("error_friendly_display")
    if "JSONDecodeError" in msg or "Expecting value" in msg:
        return t("error_friendly_parse")
    if "Errno 2" in msg or "No such file" in msg or "FileNotFoundError" in msg:
        s = msg.rfind("/")
        fname = msg[s:] if s > 0 else msg
        return t("error_friendly_file_not_found", path=f"...{fname[:40]}")
    if "Errno 13" in msg or "Permission denied" in msg or "PermissionError" in msg:
        return t("error_friendly_permission")
    if "Errno 21" in msg or "Is a directory" in msg or "IsADirectoryError" in msg:
        return t("error_friendly_is_directory")
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return t("error_friendly_timeout")
    if "ConnectionError" in msg or "Connection refused" in msg:
        return t("error_friendly_connection")
    if "401" in msg or "Unauthorized" in msg or "API key" in msg.lower():
        return t("error_friendly_auth")
    if "402" in msg or "Payment Required" in msg:
        return t("error_friendly_billing")
    if "429" in msg or "Rate limit" in msg or "Too Many Requests" in msg:
        return t("error_friendly_rate_limit")
    if "ModuleNotFoundError" in msg or "No module named" in msg:
        m = msg.split("'")[1] if "'" in msg else "?"
        return t("error_friendly_missing_module", package=m)
    if "chromadb" in msg.lower() or "Expected embeddings" in msg:
        return t("error_friendly_memory")
    return None


def print_status_bar(text: str):
    txt = Text()
    txt.append(f"{INDENT}{text}", style=f"italic {DIM}")
    console.print(txt)


def print_divider():
    console.print()


def print_separator():
    txt = Text("-" * 40, style=DIM)
    console.print(txt)


def print_markdown(text: str):
    console.print(Markdown(text))


def print_table(title: str, columns: list[str], rows: list[list[str]]):
    from rich.table import Table
    table = Table(title=title, title_style=f"bold {ORANGE}", border_style=DIM, box=box.HORIZONTALS)
    for c in columns:
        table.add_column(c, style=ORANGE)
    for r in rows:
        table.add_row(*[escape(str(cell)) for cell in r])
    console.print(table)


def print_error(text: str):
    txt = Text()
    txt.append(INDENT + "✗ ", style=ORANGE)
    txt.append(t("label_error") + ": ", style="bold")
    txt.append(str(text))
    console.print(txt)


def print_success(text: str):
    txt = Text()
    txt.append(INDENT + "✓ ", style=GREEN)
    txt.append(str(text))
    console.print(txt)


def print_warning(text: str):
    """Warning message — orange warning style."""
    txt = Text()
    txt.append(INDENT + "⚠ ", style="bold #FFA500")
    txt.append(str(text), style="#FFA500")
    console.print(txt)


def print_info(text: str):
    if modes.is_on('godmode'):
        color = "#ff3333"
    elif modes.is_on('audit'):
        color = "#E06C75"
    else:
        color = USER

    txt = Text()
    txt.append(f"{INDENT}{text}", style=color)
    console.print(txt)


def print_panel(text: str, title: str = ""):
    console.print(Panel(Text(text), title=title, border_style=DIM, box=box.ROUNDED))

def print_session_summary(duration_sec: float, turn_count: int, tokens_in: int, tokens_out: int, cost: float):
    from rich.panel import Panel
    from rich.table import Table
    from rich.align import Align

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="yellow")

    mins = int(duration_sec // 60)
    secs = int(duration_sec % 60)
    time_str = t("session_summary_min_sec", mins=mins, secs=secs) if mins > 0 else t("session_summary_seconds", secs=secs)

    table.add_row("⏱️  " + t("session_summary_duration"), time_str)
    table.add_row("🔄 " + t("session_summary_turns"), str(turn_count))
    table.add_row("📥 " + t("session_summary_tokens_in"), f"{tokens_in:,}")
    table.add_row("📤 " + t("session_summary_tokens_out"), f"{tokens_out:,}")
    if cost > 0:
        table.add_row("💰 " + t("session_summary_cost"), f"${cost:.4f}")

    panel = Panel(
        Align.left(table),
        title="[bold green]" + t("session_summary_title") + "[/bold green]",
        border_style="green",
        expand=False
    )
    console.print()
    console.print(panel)
    console.print()
