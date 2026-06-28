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
import time as _time

_RE_FILE_LINE = _re.compile(r'File "([^"]+)", line (\d+)')
_RE_FILE_LINE2 = _re.compile(r'[-\s]+File "([^"]+)", line (\d+)')

console = Console()

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
    "batch python": "\U0001F9E9",
}

_ARG_LABEL_KEYS = {"path","code","command","query","question","prompt","message","pattern","text","url"}


def _icon(name: str) -> str:
    nl = name.lower().replace("_", " ")
    for k, v in _emoji.items():
        if k in nl:
            return v
    return "\u26A1"


def _safe_str(s: str, max_len: int = 120) -> str:
    return str(s or "").strip()[:max_len]


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
    console.print(f"[bold {ORANGE}]> Dorina :[/bold {ORANGE}]")
    console.print(Markdown(message), justify="left")
    console.print()


def print_assistant_stream(chunk: str):
    global _stream_buffer
    with _stream_lock:
        _stream_buffer += chunk
        if (len(_stream_buffer) >= 40
                or _stream_buffer.endswith(("\n", ". ", "! ", "? ", ": ", "; "))):
            console.print(_stream_buffer, end="", highlight=False, markup=False)
            _stream_buffer = ""


_stream_buffer = ""
_stream_lock = _threading.Lock()


def flush_stream():
    global _stream_buffer
    with _stream_lock:
        if _stream_buffer:
            console.print(_stream_buffer, end="", highlight=False, markup=False)
            _stream_buffer = ""


def print_tool_start(name: str, args: dict | None = None):
    global _tool_start_time
    _tool_start_time = _time.time()
    console.print()
    t = Text()
    t.append(f"  {_icon(name)} ", style=GREEN)
    t.append(name.replace("_", " ").title(), style="bold")
    if args:
        matched = {k for k in args if k in _ARG_LABEL_KEYS}
        if matched:
            key = matched.pop()
            val = str(args.get(key, ""))
            if key == "code":
                val = val.replace("\n", "\\n")
            _label = _safe_str(val, 60)
            if _label:
                t.append(f": {_label}", style=DIM)
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
                    t = Text()
                    t.append(f"(+{len(r)-3} daha)", style=DIM)
                    console.print("      ", end="")
                    console.print(t)
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
    raw = str(error or "")
    msg = raw[:120]
    if raw.strip().startswith("{"):
        try:
            p = _json.loads(raw)
            msg = p.get("error", "") or p.get("message", "") or msg
        except Exception:
            pass
    user_msg = _friendly_error(msg)
    import logging as _logging
    _logging.getLogger("dorina").debug(f"Tool hatasi [{name}]: {raw[:300]}")
    location = _find_error_location(raw)
    t = Text()
    t.append("    \u2717 ", style=ORANGE)
    t.append(user_msg or msg)
    if location:
        t.append(" ", style="")
        t.append(location, style=DIM)
    console.print(t)


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
        return "Arayuz bileseni hatasi (Detay: log)"
    if "MarkupError" in msg:
        return "Goruntu bileseni hatasi (Detay: log)"
    if "JSONDecodeError" in msg or "Expecting value" in msg:
        return "Beklenmeyen yanit formati (Detay: log)"
    if "Errno 2" in msg or "No such file" in msg or "FileNotFoundError" in msg:
        s = msg.rfind("/")
        fname = msg[s:] if s > 0 else msg
        return f"Dosya bulunamadi: ...{fname[:40]}"
    if "Errno 13" in msg or "Permission denied" in msg or "PermissionError" in msg:
        return "Erisim izni yok"
    if "Errno 21" in msg or "Is a directory" in msg or "IsADirectoryError" in msg:
        return "Bu bir dizin, dosya yolu belirtin"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "Baglanti zamani asti"
    if "ConnectionError" in msg or "Connection refused" in msg:
        return "Baglanti kurulamadi"
    if "401" in msg or "Unauthorized" in msg or "API key" in msg.lower():
        return "API anahtari gecersiz"
    if "402" in msg or "Payment Required" in msg:
        return "API kredisi tukendi"
    if "429" in msg or "Rate limit" in msg or "Too Many Requests" in msg:
        return "Cok fazla istek, bekleyin"
    if "ModuleNotFoundError" in msg or "No module named" in msg:
        m = msg.split("'")[1] if "'" in msg else "?"
        return f"Eksik paket: {m}"
    if "chromadb" in msg.lower() or "Expected embeddings" in msg:
        return "Bellek sistemi hatasi (Detay: log)"
    return None


def print_status_bar(text: str):
    t = Text()
    t.append(f"  {text}", style=f"italic {DIM}")
    console.print(t)


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
