"""Baslangic banner'i — fastfetch tarzi, #D4622A tema."""
import os
import platform
import sys
from rich.console import Console
from rich.text import Text

from core.constants import VERSION

# ── Renk paleti (#D4622A turuncu tema) ─────────────
V1    = "#D4622A"   # ana turuncu
V2    = "#E08F5A"   # acik turuncu
V3    = "#D4A03A"   # altin
DIM   = "#8A8478"   # sicak gri
HI    = "#F0EAD8"   # sicak beyaz
GREEN = "#6BB05D"   # sicak yesil
AMBER = "#D4A03A"   # altin
CORAL = "#D4622A"   # turuncu
TEAL  = "#5BA0A0"   # sicak teal

console = Console()

# ── ASCII art (6 satir, gradient) ───────────────────
_ASCII_LINES = [
    f"[{V1}]██████╗  ██████╗ ██████╗ ██╗███╗   ██╗ █████╗ [/{V1}]",
    f"[{V2}]██╔══██╗██╔═══██╗██╔══██╗██║████╗  ██║██╔══██╗[/{V2}]",
    f"[{V1}]██║  ██║██║   ██║██████╔╝██║██╔██╗ ██║███████║[/{V1}]",
    f"[{V2}]██║  ██║██║   ██║██╔══██╗██║██║╚██╗██║██╔══██║[/{V2}]",
    f"[{V1}]██████╔╝╚██████╔╝██║  ██║██║██║ ╚████║██║  ██║[/{V1}]",
    f"[{V3}]╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝[/{V3}]",
]

_ASCII_HEIGHT = len(_ASCII_LINES)


def _kv(key: str, val: str, key_w: int = 10) -> Text:
    t = Text()
    t.append(f"{key:<{key_w}}", style=f"bold {V2}")
    t.append(" ", style="")
    t.append_text(Text.from_markup(val))
    return t


def _dim(s: str) -> str:
    return f"[{DIM}]{s}[/{DIM}]"


def _hi(s: str) -> str:
    return f"[{HI}]{s}[/{HI}]"


def _color(s: str, c: str) -> str:
    return f"[{c}]{s}[/{c}]"


def _build_info_lines(
    model_info: str,
    session_id: str,
    tools_available: list[str],
    tools_all: list[tuple[str, str]],
    skills: list[tuple[str, str]],
    api_keys: list[str],
) -> list[Text]:
    lines: list[Text] = []

    header = Text()
    header.append("DORINA", style=f"bold {V1}")
    header.append("@", style=f"{DIM}")
    header.append("studio", style=f"bold {V2}")
    lines.append(header)

    sep = Text("\u2500" * 36, style=DIM)
    lines.append(sep)

    provider, _, model_name = model_info.partition("/")
    lines.append(_kv("model", _hi(model_name) + " " + _dim("· " + provider)))
    lines.append(_kv("session", _color(session_id[:8], V3) + " " + _dim("· auto-save")))
    lines.append(_kv("cwd", _dim(os.getcwd()[-40:])))

    if api_keys:
        keys_str = _color(", ".join(api_keys[:3]), TEAL)
        if len(api_keys) > 3:
            keys_str += _dim(" +" + str(len(api_keys) - 3))
        lines.append(_kv("api keys", keys_str))
    else:
        lines.append(_kv("api keys", _color("yok", CORAL)))
    lines.append(Text(""))

    tool_count = len(tools_available)
    cat_count = 15
    lines.append(_kv("tools", _color(str(tool_count), GREEN) + " " + _dim("active · " + str(cat_count) + " categories")))
    skill_count = len(skills)
    if skill_count:
        sk_str = _color(str(skill_count), AMBER) + " " + _dim("loaded")
    else:
        sk_str = _dim("henuz yok · ogrenmek icin kullan")
    lines.append(_kv("skills", sk_str))
    lines.append(Text(""))

    lines.append(_kv("state", _color("IDLE", GREEN) + " " + _dim("· 9-state machine")))
    lines.append(_kv("memory", _hi("semantic") + " " + _dim("+ episodic + procedural")))
    lines.append(_kv("rag", _color("chromadb", GREEN) + " " + _dim("· initialized")))
    lines.append(_kv("version", _color("v" + VERSION, V3) + " " + _dim("· python " + sys.version.split()[0])))

    uname = platform.uname()
    lines.append(_kv("platform", _dim(f"{uname.system} {uname.machine}")))
    lines.append(Text(""))

    swatches = Text()
    for color in [V1, V2, V3, DIM, GREEN, AMBER, CORAL, TEAL]:
        swatches.append("███", style=color)
    lines.append(swatches)

    return lines


def print_startup_banner(
    model_info: str,
    session_id: str,
    tools_available: list[str],
    tools_all: list[tuple[str, str]],
    skills: list[tuple[str, str]],
    api_keys: list[str],
):
    info_lines = _build_info_lines(
        model_info, session_id, tools_available, tools_all, skills, api_keys
    )

    total = max(_ASCII_HEIGHT, len(info_lines))
    ascii_padded = _ASCII_LINES + [""] * (total - _ASCII_HEIGHT)
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
    console.print(f"  [{HI}]Hos geldin![/{HI}] [{DIM}]Ne yapalim?[/{DIM}]")
    console.print()
