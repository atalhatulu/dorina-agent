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

from prompt_toolkit.output import create_output
from prompt_toolkit.patch_stdout import patch_stdout as _pt_patch

console = Console(
    highlight=False,
)

_tool_outputs: list[dict] = []

def store_tool_output(name: str, result: str):
    """Tool çıktısını sakla, ctrl+o ile expand edilebilir."""
    _tool_outputs.append({
        "name": name,
        "result": result,
        "expanded": False,
        "index": len(_tool_outputs),
    })

def expand_last_tool():
    """Son tool çıktısını ekrana bas."""
    if not _tool_outputs:
        return
    last = _tool_outputs[-1]
    console.print()
    console.print(f"  [dim]── {last['name']} output ──[/dim]")
    lines = last["result"].split("\n")[:50]
    for line in lines:
        console.print(f"  {line}", highlight=False, markup=False)
    if len(last["result"].split("\n")) > 50:
        console.print(f"  [dim]... ({len(last['result'].split(chr(10)))-50} satır daha)[/dim]")
    console.print()

def clear_tool_outputs():
    """Yeni session başlangıcında temizle."""
    _tool_outputs.clear()

INDENT = "  "

ORANGE = "#D4622A"
TEXT   = "#F0EAD8"
USER   = "#E08F5A"
DIM    = "#8A8478"
GREEN  = "#6BB05D"

_stream_started = False

def _safe_str(s: str, max_len: int = 120) -> str:
    return str(s or "").strip()[:max_len]


def print_user(message: str):
    t = Text()
    t.append(INDENT + "> ", style=f"bold {USER}")
    t.append(message, style=f"italic {TEXT}")
    console.print(t)


def print_assistant(message: str):
    message = _re.sub(r'<[^>]+>.*?</[^>]+>', '', message, flags=_re.DOTALL)
    message = _re.sub(r'\n\s*\n\s*\n+', '\n\n', message).strip()
    if not message:
        return
    console.print()
    width = console.width - 4
    md_console = Console(width=width, highlight=False, soft_wrap=False)
    from rich.padding import Padding
    padded_md = Padding(Markdown(message), (0, 0, 0, 2)) # Üst, Sağ, Alt, Sol
    md_console.print(padded_md, justify="left")
    console.print()


def print_assistant_stream(chunk: str):
    global _stream_buffer, _stream_started
    with _stream_lock:
        if not _stream_started and chunk:
            # İlk chunk'ta INDENT ekle
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
        _stream_started = False  # ← sonraki yanıt için sıfırla


_current_tool_text = None

def print_tool_start(name: str, args: dict | None = None):
    global _tool_start_time, _current_tool_text
    _tool_start_time = _time.time()
    
    pascal_name = "".join(word.capitalize() for word in name.split("_"))
    arg_str = ""
    if args:
        matched = {k for k in args if k in {"path","code","command","query","question","prompt","message","pattern","text","url"}}
        if matched:
            key = matched.pop()
            val = str(args.get(key, ""))
            if key == "code":
                val = val.replace("\n", "\\n")
            arg_str = _safe_str(val, 60)
            
    t = Text()
    t.append(INDENT)
    t.append("● ", style=DIM)
    t.append(f"{pascal_name}", style="bold")
    t.append(f"({arg_str})", style=DIM)
    
    _current_tool_text = t
    console.print(t, end="")


def print_tool_done(name: str, result: str):
    store_tool_output(name, result)
    global _tool_start_time, _current_tool_text
    _duration = f" (~{max(0.0, _time.time() - _tool_start_time):.1f}s)" if _tool_start_time else ""
    _tool_start_time = 0
    raw = str(result or "").strip()
    is_multi = "\n" in raw[:200]
    summary = raw[:120]

    try:
        data = _json.loads(result) if result.startswith("{") else {}
        if "error" in data:
            err_msg = _safe_str(data["error"], 100)
            if _current_tool_text:
                console.print(f" → [italic {ORANGE}]Error: {err_msg}[/italic {ORANGE}]")
                _current_tool_text = None
            else:
                console.print(f"{INDENT}→ [italic {ORANGE}]Error: {err_msg}[/italic {ORANGE}]")
            return
        if "path" in data:
            summary = f"{data['path']} ({data.get('bytes','?')} B)"
        elif "results" in data:
            r = data["results"]
            if r and isinstance(r[0], dict) and "title" in r[0]:
                summary = f"{len(r)} sonuç"
            else:
                summary = f"{len(r)} sonuç"
        elif "note" in data:
            summary = data["note"][:150]
        elif data.get("success"):
            summary = data.get("message", "Başarılı")
    except Exception:
        pass

    if is_multi:
        fl = _safe_str(raw.split("\n")[0], 100)
        summary = f"{fl} ({raw.count(chr(10))+1} satır, {len(raw)} B)"

    if _current_tool_text:
        console.print(f" → {_safe_str(summary, 120)}{_duration}", style=DIM)
        _current_tool_text = None
    else:
        console.print(f"{INDENT}→ {_safe_str(summary, 120)}{_duration}", style=DIM)


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
    t.append(INDENT + "\u2717 ", style=ORANGE)
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
    t.append(f"{INDENT}{text}", style=f"italic {DIM}")
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
    t.append(INDENT + "\u2717 ", style=ORANGE)
    t.append("Hata: ", style="bold")
    t.append(str(text))
    console.print(t)


def print_success(text: str):
    t = Text()
    t.append(INDENT + "\u2713 ", style=GREEN)
    t.append(str(text))
    console.print(t)


def print_info(text: str):
    from core.config import settings
    import soul.personality as _sp
    godmode = getattr(settings.model, "godmode", False)
    
    if godmode:
        color = "#ff3333"
    elif getattr(_sp, "AUDIT_MODE", False):
        color = "#E06C75"
    else:
        color = USER
    
    t = Text()
    t.append(f"{INDENT}{text}", style=color)
    console.print(t)


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
    time_str = f"{mins}dk {secs}sn" if mins > 0 else f"{secs} saniye"

    table.add_row("⏱️  Süre:", time_str)
    table.add_row("🔄 Tur Sayısı:", str(turn_count))
    table.add_row("📥 Gelen Token:", f"{tokens_in:,}")
    table.add_row("📤 Çıkan Token:", f"{tokens_out:,}")
    if cost > 0:
        table.add_row("💰 Maliyet:", f"${cost:.4f}")

    panel = Panel(
        Align.left(table),
        title="[bold green]Oturum Özeti[/bold green]",
        border_style="green",
        expand=False
    )
    console.print()
    console.print(panel)
    console.print()
