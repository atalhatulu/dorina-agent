"""Terminal UI - #D4622A turuncu tema, Text.append ile guvenli."""
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from rich import box
import re as _re
import json as _json
import threading as _threading

console = Console()

# Renk paleti (#D4622A turuncu tema)
ORANGE = "#D4622A"
TEXT   = "#F0EAD8"
USER   = "#E08F5A"
DIM    = "#8A8478"
GREEN  = "#6BB05D"

_emoji = {
    "read file": "\U0001F4D6", "write file": "\U0001F4C4", "patch": "\U0001F527",
    "terminal": "\U0001F4BB", "web search": "\U0001F50D", "web fetch": "\U0001F310",
    "search files": "\U0001F50E", "browser": "\U0001F30D", "delegate": "\U0001F9E0",
    "git add": "\u2795", "git commit": "\U0001F4DD", "git diff": "\U0001F4CA", "git push": "\u2B06",
    "git branch": "\U0001F33F", "git log": "\U0001F4CB", "git status": "\U0001F4CC",
    "system info": "\U0001F5A5", "ps": "\U0001F4CA", "disk usage": "\U0001F4BE",
    "tree": "\U0001F333", "ping": "\U0001F4E1", "weather": "\U0001F324",
    "deep research": "\U0001F52C", "backup": "\U0001F4BF", "timer": "\u23F1",
    "save preference": "\u2699", "list tools": "\U0001F9F0",
}


def _icon(name: str) -> str:
    nl = name.lower().replace("_", " ")
    for k, v in _emoji.items():
        if k in nl:
            return v
    return "\u26A1"


def _safe_str(s: str, max_len: int = 120) -> str:
    return str(s or "").strip()[:max_len]


# ── Kullanici / Asistan ──────────────────────────────

def print_user(message: str):
    t = Text()
    t.append("> ", style=f"bold {USER}")
    t.append(message, style=f"italic {TEXT}")
    console.print(t)


def print_assistant(message: str):
    message = _re.sub(r'<[^>]+>.*?</[^>]+>', '', message, flags=_re.DOTALL)
    message = _re.sub(r'\n\s*\n\s*\n+', '\n\n', message).strip()
    if not message:
        return
    console.print()
    console.print(f"[bold {ORANGE}]# Dorina #[/bold {ORANGE}]")
    console.print(Markdown(message), justify="left")
    console.print()


def print_assistant_stream(chunk: str):
    global _stream_buffer
    _stream_buffer += chunk
    if (len(_stream_buffer) >= 40
            or _stream_buffer.endswith(("\n", ". ", "! ", "? ", ": ", "; "))):
        console.print(_stream_buffer, end="", highlight=False, markup=False)
        _stream_buffer = ""


_stream_buffer = ""


def flush_stream():
    global _stream_buffer
    if _stream_buffer:
        console.print(_stream_buffer, end="", highlight=False, markup=False)
        _stream_buffer = ""


# ── Tool ciktilari ───────────────────────────────────

def print_tool_start(name: str):
    console.print()
    t = Text()
    t.append(f"  {_icon(name)} ", style=GREEN)
    t.append(name.replace("_", " ").title(), style="bold")
    t.append("...", style=DIM)
    console.print(t)


def print_tool_done(name: str, result: str):
    raw = str(result or "").strip()
    is_multi = "\n" in raw[:200]
    summary = raw[:120]

    try:
        data = _json.loads(result) if result.startswith("{") else {}
        if "error" in data:
            t = Text()
            t.append("    \u2717 ", style=ORANGE)
            t.append(_safe_str(data["error"], 100))
            console.print(t)
            return
        if "path" in data:
            summary = f"{data['path']} ({data.get('bytes','?')} B)"
        elif "results" in data:
            r = data["results"]
            if r and isinstance(r[0], dict) and "title" in r[0]:
                for item in r[:3]:
                    t = Text()
                    t.append("    \u2713 ", style=GREEN)
                    t.append(item.get("title", "")[:60], style=USER)
                    console.print(t)
                if len(r) > 3:
                    console.print(f"      [{DIM}](+{len(r)-3} daha)[/{DIM}]")
                return
            summary = f"{len(r)} sonuc"
        elif "note" in data:
            summary = data["note"][:150]
        elif data.get("success"):
            summary = data.get("message", "Basarili")
        is_multi = False
    except Exception:
        pass

    if is_multi:
        fl = _safe_str(raw.split("\n")[0], 100)
        t = Text()
        t.append("    \u2713 ", style=GREEN)
        t.append(fl)
        console.print(t)
        t2 = Text()
        t2.append(f"      ({raw.count(chr(10))+1} satir, {len(raw)} B)", style=DIM)
        console.print(t2)
    else:
        t = Text()
        t.append("    \u2713 ", style=GREEN)
        t.append(_safe_str(summary, 120))
        console.print(t)


def print_tool_error(name: str, error: str):
    msg = _safe_str(error, 120)
    if str(error or "").strip().startswith("{"):
        try:
            p = _json.loads(str(error))
            e = p.get("error", "") or p.get("message", "")
            if e:
                msg = _safe_str(e, 120)
                msg = msg.replace("[Errno 13] Permission denied", "Izin reddedildi")
                msg = msg.replace("[Errno 21] Is a directory", "Bu bir dizin, dosya degil")
                msg = msg.replace("[Errno 2] No such file or directory", "Dosya/dizin bulunamadi")
        except Exception:
            pass
    t = Text()
    t.append("    \u2717 ", style=ORANGE)
    t.append(msg)
    console.print(t)


def print_status_bar(text: str):
    t = Text()
    t.append(f"  {text}", style=f"italic {DIM}")
    console.print(t)


# ── Kisa fonksiyonlar ────────────────────────────────

def print_divider():
    console.print()


def print_separator():
    t = Text("-" * 40, style=DIM)
    console.print(t)


def print_markdown(text: str):
    console.print(Markdown(text))


def print_table(title: str, columns: list[str], rows: list[list[str]]):
    from rich.table import Table
    t = Table(title=title, title_style=f"bold {ORANGE}", border_style=DIM, box=box.HORIZONTALS)
    for c in columns:
        t.add_column(c, style=ORANGE)
    for r in rows:
        t.add_row(*[escape(str(cell)) for cell in r])
    console.print(t)


def print_error(text: str):
    t = Text()
    t.append("  \u2717 ", style=ORANGE)
    t.append("Hata: ", style="bold")
    t.append(str(text))
    console.print(t)


def print_success(text: str):
    t = Text()
    t.append("  \u2713 ", style=GREEN)
    t.append(str(text))
    console.print(t)


def print_info(text: str):
    t = Text()
    t.append(f"  {text}", style=USER)
    console.print(t)


def print_panel(text: str, title: str = ""):
    console.print(Panel(Text(text), title=title, border_style=DIM, box=box.ROUNDED))
