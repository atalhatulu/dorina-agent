"""Interactive provider selector using prompt_toolkit RadioList dialog."""
from __future__ import annotations
from typing import Optional

from rich.console import Console

console = Console()

PROVIDERS = [
    ("deepseek",     "DeepSeek (V3, R1, coder, direct API)"),
    ("openrouter",   "OpenRouter (Pay-per-use API aggregator, 200+ models)"),
    ("groq",         "Groq (Free tier, very fast inference)"),
    ("openai",       "OpenAI (GPT-4o, GPT-4.1, Codex CLI)"),
    ("anthropic",    "Anthropic (Claude models via API)"),
    ("google",       "Google AI Studio (Native Gemini API)"),
    ("siliconflow",  "SiliconFlow (China, free tier, DeepSeek models)"),
    ("ollama",       "Ollama (Local, 127.0.0.1:11434, no key needed)"),
    ("together",     "Together AI (Open-source model hosting)"),
]


def select_provider(current: str = "") -> str | None:
    """Interactive provider selector using prompt_toolkit RadioList dialog.
    
    Keyboard: ↑↓ navigate, ENTER select, ESC/q cancel.
    """
    try:
        from prompt_toolkit.shortcuts.dialogs import radiolist_dialog
        from prompt_toolkit.shortcuts import input_dialog
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style

        # Build values list
        values = []
        default = None
        for name, desc in PROVIDERS:
            label = f"{name} — {desc}"
            values.append((name, label))
            if name == current:
                default = name

        style = Style([
            ("dialog", "bg:#1a1815"),
            ("dialog.body", "bg:#1a1815 fg:#ffffff"),
            ("dialog.body label", "fg:#ffffff"),
            ("dialog.body selected-text", "fg:#D4622A bold"),
            ("dialog.body checkbox", "fg:#D4622A"),
            ("dialog.body selected-checkbox", "fg:#D4622A"),
            ("button", "fg:#ffffff bg:#D4622A"),
            ("dialog.title", "fg:#D4622A bold"),
        ])

        result = radiolist_dialog(
            title="Select Provider",
            text="↑↓ navigate  ENTER select  ESC cancel:",
            values=values,
            default=default,
            style=style,
        ).run()

        return result

    except Exception:
        return _fallback_provider_selector(current)


def _fallback_provider_selector(current: str) -> str | None:
    """Simple numbered list fallback."""
    console.print("\n[bold]Select Provider:[/bold]")
    console.print("[dim]Enter number or 'q' to cancel[/dim]\n")

    for i, (name, desc) in enumerate(PROVIDERS, 1):
        marker = "●" if name == current else "○"
        console.print(f"  ({marker}) {name} — {desc}")

    while True:
        try:
            choice = input("\n  > ").strip().lower()
            if choice in ("q", "cancel", ""):
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDERS):
                return PROVIDERS[idx][0]
            console.print(f"  [red]Invalid: enter 1-{len(PROVIDERS)}[/red]")
        except (ValueError, EOFError):
            console.print(f"  [red]Enter a number (1-{len(PROVIDERS)})[/red]")
        except KeyboardInterrupt:
            return None
