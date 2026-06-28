"""Başlangıç banner'ı — atalhatulu.com renk temalı."""

import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich import box
from rich.text import Text

from core.constants import VERSION

# atalhatulu.com renk paleti
BG = "#1a1815"
ORANGE = "#D4622A"
TEXT = "#f0ead8"
DIM = "#8a8478"
GREEN = "#6bb05d"
YELLOW = "#d4a03a"

console = Console()


def print_startup_banner(
    model_info: str,
    session_id: str,
    tools_available: list[str],
    tools_all: list[tuple[str, str]],
    skills: list[tuple[str, str]],
    api_keys: list[str],
):
    """Hermes tarzı açılış ekranı — atalhatulu teması."""

    logo = f"""
[bold {ORANGE}]██████╗  ██████╗ ██████╗ ██╗███╗   ██╗ █████╗ 
██╔══██╗██╔═══██╗██╔══██╗██║████╗  ██║██╔══██╗
██║  ██║██║   ██║██████╔╝██║██╔██╗ ██║███████║
██║  ██║██║   ██║██╔══██╗██║██║╚██╗██║██╔══██║
██████╔╝╚██████╔╝██║  ██║██║██║ ╚████║██║  ██║
╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
[/bold {ORANGE}]
"""

    info_tbl = Table.grid(padding=(0, 1))
    info_tbl.add_column(style=DIM, width=10)
    info_tbl.add_column(style=TEXT)
    info_tbl.add_row("Model:", model_info)
    info_tbl.add_row("Session:", session_id[:16])
    info_tbl.add_row("Directory:", os.getcwd())
    info_tbl.add_row("API Keys:", ", ".join(api_keys) if api_keys else "yok")
    info_panel = Panel(info_tbl, title=f"[bold {ORANGE}]System[/bold {ORANGE}]",
                       border_style=ORANGE, box=box.ROUNDED, padding=(1, 2))

    tools_tbl = Table.grid(padding=(0, 2))
    tools_tbl.add_column(style=GREEN, width=16)
    tools_tbl.add_column(style=DIM, width=20)
    max_display = 15
    for i, (name, desc) in enumerate(tools_all):
        if i >= max_display:
            remaining = len(tools_all) - max_display
            tools_tbl.add_row(f"[dim]+{remaining} more[/dim]", "[dim]use /tools to list all[/dim]")
            break
        tools_tbl.add_row(name, desc)
    tools_panel = Panel(tools_tbl, title=f"[bold {ORANGE}]Tools[/bold {ORANGE}]",
                        border_style=ORANGE, box=box.ROUNDED, padding=(1, 2))

    skills_tbl = Table.grid(padding=(0, 2))
    skills_tbl.add_column(style=YELLOW, width=16)
    skills_tbl.add_column(style=DIM, width=20)
    if skills:
        for name, desc in skills:
            skills_tbl.add_row(name, desc)
    else:
        skills_tbl.add_row("(henuz yok)", "ogrenmek icin kullan")
    skills_panel = Panel(skills_tbl, title=f"[bold {ORANGE}]Skills[/bold {ORANGE}]",
                         border_style=ORANGE, box=box.ROUNDED, padding=(1, 2))

    main_content = Columns([info_panel, tools_panel, skills_panel], equal=False)
    main_panel = Panel(main_content,
                       border_style=ORANGE,
                       box=box.HEAVY,
                       padding=(1, 2))

    footer = Text()
    footer.append(f"  {len(tools_available)} tools", style=GREEN)
    footer.append(" · ", style=DIM)
    footer.append(f"{len(skills)} skills", style=YELLOW)
    footer.append(" · ", style=DIM)
    footer.append("/help for commands", style=ORANGE)
    footer.append(" · ", style=DIM)
    footer.append(f"v{VERSION}", style=DIM)

    console.print()
    console.print(logo)
    console.print(main_panel)
    console.print()
    console.print(footer)
    console.print()
    console.print(f"[bold {TEXT}]Hos geldin![/bold {TEXT}] Sana nasil yardimci olabilirim?")
    console.print()
