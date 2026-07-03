"""Interactive provider/model selector using prompt_toolkit.

Pattern: custom Application + FormattedTextControl + KeyBindings.
NO Dialog/RadioList (RadioList consumes Enter).
Uses _pick_one() with idx[0] closure, e.app.invalidate() on nav,
Enter/Space=submit, Esc=cancel. full_screen=False (no terminal takeover).
"""
from __future__ import annotations
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, FormattedTextControl, Window, Container, Float, FloatContainer
from rich.console import Console
from core.constants import t
from providers.keys import keys, PROVIDERS

console = Console()


async def _pick_one(title: str, items: list[tuple[str, str]], current: str = "") -> str | None:
    """Interactive picker with ↑↓ Space/Enter Esc (async — uses run_async)."""
    if not items:
        return None

    idx = [0]

    def _render():
        result = [("", f"\n {title}\n" + "─" * 40 + "\n")]
        for i, (pid, disp) in enumerate(items):
            prefix = " ● " if pid == current else " ○ "
            if i == idx[0]:
                result.append(("class:selected", f"▸{prefix}"))
                result.append(("class:selected bold", f"{disp:30s}"))
                _has = t("provider_key_present") if keys.has_key(pid) else t("provider_key_missing")
                result.append(("", f"  [{_has:>8}]\n"))
            else:
                result.append(("", f" {prefix}"))
                result.append(("", f"{disp:30s}  "))
                key_status = ("green" if keys.has_key(pid) else "red")
                _has = t("provider_key_present") if keys.has_key(pid) else t("provider_key_missing")
                result.append((key_status, f"[{_has:>8}]\n"))
        result.append(("dim", "\n ↑↓ navigate  Enter/Space select  Esc cancel\n"))
        return result

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        idx[0] = (idx[0] - 1) % len(items)
        event.app.invalidate()

    @kb.add("down")
    def _down(event):
        idx[0] = (idx[0] + 1) % len(items)
        event.app.invalidate()

    @kb.add("enter")
    @kb.add("space")
    def _submit(event):
        event.app.exit(result=items[idx[0]][0])

    @kb.add("escape")
    def _cancel(event):
        event.app.exit(result=None)

    control = FormattedTextControl(_render)
    app = Application(
        layout=Layout(Window(control)),
        key_bindings=kb,
        full_screen=False,
    )
    try:
        return await app.run_async()
    except (Exception, asyncio.CancelledError):
        return None


async def _pick_one_model(title: str, models: list[str], current: str = "") -> str | None:
    if not models:
        return None
    items = [(m, m.split("/")[-1]) for m in models]
    return await _pick_one(title, items, current)


async def select_provider(current: str = "") -> str | None:
    items = keys.list_providers()
    return await _pick_one("Select Provider:", items, current)


async def select_model(provider: str, current: str = "") -> str | None:
    models = keys.get_models(provider)
    items = [(m, m.split("/")[-1]) for m in models]
    current_model = current.split("/")[-1] if "/" in current else current
    return await _pick_one(f"Models for {provider}:", items, current_model)
