"""Startup banner — fastfetch style, #D4622A theme."""
import os
import platform
import subprocess as _sp_run
import sys
from rich.console import Console
from rich.text import Text

from core.config import settings
from core.constants import VERSION, t

# ── Color palette ─────────────
DIM   = "#8A8478"   # warm gray
HI    = "#F0EAD8"   # warm white
GREEN = "#6BB05D"   # warm green
AMBER = "#D4A03A"   # gold
TEAL  = "#5BA0A0"   # warm teal

console = Console()

def get_ascii_lines(v1, v2, v3):
    return [
        f"[{v1}]██████╗  ██████╗ ██████╗ ██╗███╗   ██╗ █████╗ [/{v1}]",
        f"[{v2}]██╔══██╗██╔═══██╗██╔══██╗██║████╗  ██║██╔══██╗[/{v2}]",
        f"[{v1}]██║  ██║██║   ██║██████╔╝██║██╔██╗ ██║███████║[/{v1}]",
        f"[{v2}]██║  ██║██║   ██║██╔══██╗██║██║╚██╗██║██╔══██║[/{v2}]",
        f"[{v1}]██████╔╝╚██████╔╝██║  ██║██║██║ ╚████║██║  ██║[/{v1}]",
        f"[{v3}]╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝[/{v3}]",
    ]


def _kv(key: str, val: str, key_w: int = 10, v2: str = "#E08F5A") -> Text:
    t_obj = Text()
    t_obj.append(f"{key:<{key_w}}", style=f"bold {v2}")
    t_obj.append(" ", style="")
    t_obj.append_text(Text.from_markup(val))
    return t_obj


def _dim(s: str) -> str:
    return f"[{DIM}]{s}[/{DIM}]"


def _hi(s: str) -> str:
    return f"[{HI}]{s}[/{HI}]"


def _color(s: str, c: str) -> str:
    return f"[{c}]{s}[/{c}]"


def _last_session_info() -> str | None:
    """Read last session duration and token count from session store."""
    try:
        from session.manager import manager as _sm
        sessions = _sm.list() if hasattr(_sm, 'list') else []
        if sessions and len(sessions) > 1:
            prev = sessions[-2]
            dur = prev.get("duration", 0) or 0
            if dur < 60:
                dur_str = f"{dur:.0f}s"
            elif dur < 3600:
                dur_str = f"{dur // 60:.0f}m {dur % 60:.0f}s"
            else:
                dur_str = f"{dur // 3600:.0f}h {(dur % 3600) // 60:.0f}m"
            tokens = prev.get("tokens_total", 0)
            if tokens:
                return f"{dur_str} · {tokens:,} tok"
            return dur_str
    except (ImportError, AttributeError, IndexError, KeyError):
        pass
    return None


def _context_bar(pct: float, width: int = 12) -> str:
    """Render context usage bar for banner."""
    filled = int(pct * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"{bar} {int(pct * 100)}%"


def _build_info_lines(
    model_info: str,
    session_id: str,
    tools_available: list[str],
    tools_all: list[tuple[str, str]],
    skills: list[tuple[str, str]],
    api_keys: list[str],
    v1: str,
    v2: str,
    v3: str,
    coral: str,
    startup_duration: float = 0.0,
) -> list[Text]:
    lines: list[Text] = []

    header = Text()
    header.append("DORINA", style=f"bold {v1}")
    header.append("@", style=f"{DIM}")
    header.append("studio", style=f"bold {v2}")
    lines.append(header)

    sep = Text("─" * 36, style=DIM)
    lines.append(sep)

    provider, _, model_name = model_info.partition("/")
    lines.append(_kv("model", _hi(model_name) + " " + _dim("· " + provider), v2=v2))
    lines.append(_kv("session", _color(session_id[:8], v3) + " " + _dim("· auto-save"), v2=v2))
    lines.append(_kv("cwd", _dim(os.getcwd()[-40:]), v2=v2))

    if api_keys:
        keys_str = _color(", ".join(api_keys[:3]), TEAL)
        if len(api_keys) > 3:
            keys_str += _dim(" +" + str(len(api_keys) - 3))
        lines.append(_kv("api keys", keys_str, v2=v2))
    else:
        lines.append(_kv("api keys", _color(t("provider_key_missing"), coral), v2=v2))
    lines.append(Text(""))

    lines.append(_kv("state", _color("IDLE", GREEN) + " " + _dim("· 9-state machine"), v2=v2))
    lines.append(_kv("memory", _hi("semantic") + " " + _dim("+ episodic + procedural"), v2=v2))
    lines.append(_kv("rag", _color("chromadb", GREEN) + " " + _dim("· initialized"), v2=v2))

    # Startup duration line
    if startup_duration > 0:
        if startup_duration < 1.0:
            dur_str = f"{startup_duration*1000:.0f}ms"
        elif startup_duration < 60:
            dur_str = f"{startup_duration:.1f}s"
        else:
            dur_str = f"{startup_duration // 60:.0f}m {startup_duration % 60:.0f}s"
        lines.append(_kv("startup", _color(dur_str, AMBER) + " " + _dim("· ready"), v2=v2))

    lines.append(_kv("version", _color("v" + VERSION, v3) + " " + _dim("· python " + sys.version.split()[0]), v2=v2))

    # Last session info
    last_session = _last_session_info()
    if last_session:
        lines.append(_kv("previous", _dim(last_session), v2=v2))

    uname = platform.uname()
    lines.append(_kv("platform", _dim(f"{uname.system} {uname.machine}")))
    lines.append(Text(""))

    swatches = Text()
    for color in [v1, v2, v3, DIM, GREEN, AMBER, coral, TEAL]:
        swatches.append("███", style=color)
    lines.append(swatches)

    return lines


def print_startup_banner(
    model_info: str = "deepseek/deepseek-v4-flash",
    session_id: str = "",
    tools_available: list[str] = None,
    tools_all: list[tuple[str, str]] = None,
    skills: list[tuple[str, str]] = None,
    api_keys: list[str] = None,
    startup_duration: float = 0.0,
):
    """Clear screen and print gradient ASCII + info."""
    _sp_run.run("clear" if os.name == "posix" else "cls", shell=True)

    if tools_available is None: tools_available = []
    if tools_all is None: tools_all = []
    if skills is None: skills = []
    if api_keys is None: api_keys = []

    godmode = getattr(settings.model, "godmode", False)
    ACCENT = "#ff3333" if godmode else "#D4622A"
    V1 = ACCENT
    V2 = "#ff6666" if godmode else "#E08F5A"
    V3 = "#cc2222" if godmode else "#D4A03A"
    CORAL = ACCENT

    ascii_lines = get_ascii_lines(V1, V2, V3)

    info_lines = _build_info_lines(
        model_info, session_id, tools_available, tools_all, skills, api_keys,
        V1, V2, V3, CORAL, startup_duration
    )

    total = max(len(ascii_lines), len(info_lines))
    ascii_padded = ascii_lines + [""] * (total - len(ascii_lines))
    info_padded = info_lines + [Text("")] * (total - len(info_lines))

    console.print()
    for ascii_line, info_line in zip(ascii_padded, info_padded):
        left = Text.from_markup(ascii_line) if ascii_line else Text("")
        right = info_line if isinstance(info_line, Text) else Text(str(info_line))
        combined = Text()
        combined.append_text(left)
        combined.append("   ")
        combined.append_text(right)
        console.print(combined)

    console.print()
    footer = Text()
    footer.append("  ")
    footer.append(f"{len(tools_available)} tools", style=GREEN)
    footer.append(" · ", style=DIM)
    footer.append(f"{len(skills)} skills", style=AMBER)
    footer.append(" · ", style=DIM)
    footer.append("/help", style=f"bold {V2}")
    footer.append(" for commands", style=DIM)
    footer.append(" · ", style=DIM)
    footer.append(f"v{VERSION}", style=DIM)
    console.print(footer)
    console.print()
    console.print(f"  [{HI}]Welcome![/{HI}] [{DIM}]What shall we do?[/{DIM}]")
    console.print()
