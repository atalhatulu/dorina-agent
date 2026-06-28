"""Terminal UI - Modern, dengeli ve okuması kolay arayüz."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich import box
import re as _re
import json as _json

# Console instance — standalone, no Live dependency
console = Console()

# Renkler
DORINA_ORANGE = "#E06C75"
TEXT_MAIN = "#ABB2BF"      # Soft beyaz/gri (okumayı rahatlatır)
TEXT_USER = "#61AFEF"      # Kullanıcı girdileri için hafif mavi
DIM_GRAY = "#5C6370"       # İkincil detaylar ve çizgiler için
SUCCESS_GREEN = "#98C379"  # Başarılı tool/aksiyon yeşili


def print_user(message: str):
    """Kullanıcı mesajı - Belirgin ve temiz prompt gösterimi."""
    console.print()
    console.print(f"[bold {TEXT_USER}]>[/{TEXT_USER}] [italic {TEXT_MAIN}]{message}[/{TEXT_MAIN}]")


def print_assistant(message: str):
    """Dorina cevabı - Markdown render edilmiş ve net bir blok halinde."""
    message = _re.sub(r'<[^>]+>.*?</[^>]+>', '', message, flags=_re.DOTALL)
    message = _re.sub(r'\n\s*\n\s*\n+', '\n\n', message)
    message = message.strip()

    if not message:
        return

    console.print()
    console.print(f"[bold {DORINA_ORANGE}]# Dorina #[/bold {DORINA_ORANGE}]")
    md = Markdown(message)
    console.print(md, justify="left")
    console.print()


def print_tool_start(name: str):
    """Tool execution başlangıcı - Minimalist nokta gösterimi."""
    label = name.replace("_", " ").title()
    emoji = {
        "write file": "📄", "read file": "📖", "READ FILE": "📖", "patch": "🔧",
        "terminal": "💻", "web search": "🔍", "web fetch": "🌐",
        "search files": "🔎", "browser": "🌍", "delegate": "🧠",
    }
    icon = next((v for k, v in emoji.items() if k in name.lower().replace("_", " ")), "⚡")
    console.print(f"  [{SUCCESS_GREEN}]{icon}[/{SUCCESS_GREEN}] [bold]{label}[/bold]...")


def print_tool_done(name: str, result: str):
    """Tool execution sonucu - Alt satirda, okunabilir."""
    result_clean = str(result or "").strip()
    summary = result_clean[:120]
    _is_multiline = "\n" in result_clean[:200]
    
    # Cok kisa ciktilari anlamlandir
    if len(result_clean) < 15 and not result_clean.startswith("{") and not result_clean.startswith("["):
        if result_clean.upper() in ("VAR", "YOK", "OK", "DONE", "YES", "NO", "TRUE", "FALSE", "1", "0"):
            summary = f"{name}: {result_clean}"
            _is_multiline = False
    
    try:
        data = _json.loads(result) if result.startswith("{") else {}
        if "path" in data:
            summary = f"{data['path']} ({data.get('bytes', '?')} bytes)"
        elif "backup" in data:
            summary = f"Yedek: {data['backup']}"
        elif "archive" in data:
            summary = f"Arsiv: {data['archive']}"
        elif "results" in data:
            summary = f"{len(data['results'])} sonuc"
        elif "note" in data:
            summary = data['note'][:150]
        elif data.get("success"):
            summary = "Basarili"
        _is_multiline = False
    except Exception:
        pass
    
    if _is_multiline:
        # Cok satirli cikti - sadece ilk satir ozet, devami alt satirda
        _first_line = result_clean.split("\n")[0][:100]
        console.print(f"    [{SUCCESS_GREEN}]✓ {_first_line}[/{SUCCESS_GREEN}]")
        if len(result_clean) > 120:
            console.print(f"      [{DIM_GRAY}](devami kisaltildi, {len(result_clean)} bytes)[/{DIM_GRAY}]")
    else:
        console.print(f"    [{SUCCESS_GREEN}]✓ {summary}[/{SUCCESS_GREEN}]")


def print_tool_error(name: str, error: str):
    """Tool hatası - Temiz ve anlaşılır."""
    # JSON hata mesajlarini parse et, sadece anlamli kismi goster
    _msg = error[:120]
    if error.startswith("{"):
        try:
            import json as _j
            _parsed = _j.loads(error)
            _err = _parsed.get("error", "") or _parsed.get("message", "")
            if _err:
                _msg = _err[:120]
                # Yaygin hata kodlarini cevir
                _msg = _msg.replace("[Errno 13] Permission denied", "Izin reddedildi")
                _msg = _msg.replace("[Errno 21] Is a directory", "Bu bir dizin, dosya degil")
                _msg = _msg.replace("[Errno 2] No such file or directory", "Dosya veya dizin bulunamadi")
        except Exception:
            pass
    console.print(f"    [{DORINA_ORANGE}]✗ {_msg}[/{DORINA_ORANGE}]")


def print_status_bar(text: str):
    """Status bar - Hafif silik ara geçiş logları."""
    console.print(f"  [italic {DIM_GRAY}]{text}[/italic {DIM_GRAY}]")


def print_divider():
    console.print()


def print_separator():
    console.print(f"[dim {DIM_GRAY}]" + "-" * 40 + "[/dim]")


def print_markdown(text: str):
    console.print(Markdown(text))


_stream_buffer = ""


def flush_stream():
    """Flush any remaining stream buffer via Rich console."""
    global _stream_buffer
    if _stream_buffer:
        console.print(_stream_buffer, end="", highlight=False)
        _stream_buffer = ""


def print_assistant_stream(chunk: str):
    """Print streaming chunk via Rich console (patch_stdout uyumlu)."""
    global _stream_buffer
    _stream_buffer += chunk

    if (len(_stream_buffer) >= 40
            or _stream_buffer.endswith(("\n", ". ", "! ", "? ", ": ", "; "))):
        console.print(_stream_buffer, end="", highlight=False)
        _stream_buffer = ""


def print_table(title: str, columns: list[str], rows: list[list[str]]):
    from rich.table import Table
    table = Table(title=title, title_style=f"bold {DORINA_ORANGE}",
                  border_style=DIM_GRAY, box=box.HORIZONTALS)
    for col in columns:
        table.add_column(col, style=DORINA_ORANGE)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def print_error(text: str):
    console.print(f"  [{DORINA_ORANGE}]✗[/{DORINA_ORANGE}] [bold]Hata:[/bold] {text}")


def print_success(text: str):
    console.print(f"  [{SUCCESS_GREEN}]✓[/{SUCCESS_GREEN}] {text}")


def print_info(text: str):
    console.print(f"  [{TEXT_USER}]{text}[/{TEXT_USER}]")


def print_panel(text: str, title: str = ""):
    console.print(Panel(Text(text, style=TEXT_MAIN), title=title, border_style=DIM_GRAY, box=box.ROUNDED))
