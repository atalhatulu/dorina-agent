"""Interactive provider selector using prompt_toolkit RadioList dialog."""
from __future__ import annotations
from typing import Optional

from rich.console import Console
from providers.keys import PROVIDER_DISPLAY_LIST as PROVIDERS

console = Console()


def select_provider(current: str = "") -> str | None:
    """Numarali liste ile provider secimi (fallback)."""
    return _numbered_selector(current)


def _numbered_selector(current: str) -> str | None:
    """Basit numarali liste — ok tusu gerektirmez."""
    console.print()
    console.print("[bold]Select Provider:[/bold]")
    console.print("[dim]Enter number or 'q' to cancel[/dim]\n")

    for i, (name, desc) in enumerate(PROVIDERS, 1):
        marker = "\u25cf" if name == current else "\u25cb"
        console.print(f"  [#E06C75]{marker}[/#E06C75] [bold]{name}[/bold] — {desc}")

    while True:
        try:
            choice = input("\n  > ").strip().lower()
            if choice in ("q", "cancel", ""):
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDERS):
                return PROVIDERS[idx][0]
            console.print(f"  [red]Gecersiz: 1-{len(PROVIDERS)} arasi girin[/red]")
        except (ValueError, EOFError):
            console.print(f"  [red]Sayi girin (1-{len(PROVIDERS)})[/red]")
        except KeyboardInterrupt:
            return None
