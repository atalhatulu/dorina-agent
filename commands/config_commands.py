"""Config commands: /model, /godmode, /audit, /personality.

/model komutu:
  /model               → interactive provider selector + model picker
  /model key <p> <k>   → set API key for provider
  /model switch <p>    → quick switch to provider's first model
  /model list          → show all providers with key status
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DorinaApp


async def cmd_model(app: "DorinaApp", cmd: str) -> None:
    """Show/set model, provider, and API key interactively or via args."""
    from core.config import settings
    from providers.keys import keys, PROVIDERS
    from ui.display import console, print_success, print_error, print_info
    from ui.provider_selector import select_provider, select_model

    parts = cmd.split()
    if len(parts) == 1:
        # ── Interactive: show current → pick provider → pick model ──
        current_provider = settings.model.provider
        current_model = settings.model.default

        console.print("")
        console.print(f"  [#D4622A]Active:[/]  [bold]{current_model}[/]")
        console.print(f"  [#D4622A]Provider:[/] {current_provider}")
        console.print("")

        # Step 1: Pick provider
        provider = await select_provider(current_provider)
        if provider is None:
            return
        if provider == current_provider:
            # Same provider: offer to switch model
            model = await select_model(provider, current_model)
            if model is None:
                return
            keys.switch_to(provider, model)
            print_success(f"Model: {provider}/{model}")
        else:
            # Different provider: check API key
            if keys.has_key(provider):
                # Has key: ask for model
                model = await select_model(provider)
                if model is None:
                    return
                keys.switch_to(provider, model)
                print_success(f"Switched to {provider}/{model}")
            else:
                # No key: prompt for it
                print_info(f"{provider}: API key gerekli")
                console.print(f"  /model key {provider} <api_key>")
                return

    elif len(parts) >= 4 and parts[1] == "key":
        # ── /model key <provider> <key> ──
        prov = parts[2]
        new_key = parts[3].strip()
        keys.save_key(prov, new_key)
        print_success(f"{prov} API key guncellendi ({len(new_key)} chars)")

    elif len(parts) >= 3 and parts[1] == "switch":
        # ── /model switch <provider> ──
        prov = parts[2]
        if prov in PROVIDERS:
            models = PROVIDERS[prov].get("models", [])
            if models:
                keys.switch_to(prov, models[0])
                model_str = f"{prov}/{models[0]}" if "/" not in models[0] else models[0]
                print_success(f"Switched to {model_str}")
            else:
                print_error(f"{prov} icin model tanimli degil")
        else:
            print_error(f"Bilinmeyen provider: {prov}")

    elif len(parts) >= 2 and parts[1] == "list":
        # ── /model list ──
        console.print("")
        p = settings.model.provider
        m = settings.model.default
        console.print(f"  [#D4622A]Active:[/]  [bold]{m}[/]")
        console.print("")
        for name, info in PROVIDERS.items():
            has = keys.has_key(name)
            dot = "●" if name == p else "○"
            key_s = f"[green]KEY VAR[/]" if has else f"[dim]key yok[/dim]"
            masked = keys.get_key(name)[:10] + "..." if has and len(keys.get_key(name)) > 10 else ""
            console.print(f"  {dot} {name:14s}  {key_s}  [dim]{masked}[/dim]")
        console.print("")
        console.print("  [dim]/model key <provider> <api_key>  /model switch <provider>[/dim]")
        console.print("")

    else:
        print_error("Kullanim: /model | /model key <p> <k> | /model switch <p> | /model list")


async def cmd_godmode(app: "DorinaApp", cmd: str) -> None:
    """Toggle god mode — sinirsiz mod, guvenlik kisitlamalari kalkar."""
    from ui.display import print_success, print_error
    from ui.repl import set_style
    from core.config import settings
    from core.mode_manager import modes
    modes.toggle('godmode')
    settings.model.godmode = modes.is_on('godmode')
    settings.save()
    if modes.is_on('godmode'):
        set_style('godmode')
        print_success("GODMODE AKTIF — tum kisitlamalar kalkti")
    else:
        if modes.is_on('audit'):
            set_style('audit')
        elif modes.is_on('temp'):
            set_style('temp')
        else:
            set_style('')
        print_error("God mode kapandi — guvenlik kisitlamalari aktif")


async def cmd_audit(app: "DorinaApp", cmd: str) -> None:
    """Toggle audit mode."""
    from ui.display import print_success, print_error
    from ui.repl import set_style
    from core.mode_manager import modes
    modes.toggle('audit')
    if modes.is_on('audit'):
        set_style('audit')
        print_success("AUDIT MOD AKTIF")
    else:
        if modes.is_on('godmode'):
            set_style('godmode')
        elif modes.is_on('temp'):
            set_style('temp')
        else:
            set_style('')
        print_error("Audit mod kapandi")


async def cmd_mods(app: "DorinaApp", cmd: str) -> None:
    """Show active modes: godmode, audit, temp, speed, strict, silent, deep."""
    from core.mode_manager import modes
    from ui.display import console

    console.print("")
    console.print("  [bold]Aktif Modlar[/bold]")
    console.print("  ─────────────")
    _god = "[bold #ff3333]GOD MODE[/bold #ff3333]" if modes.is_on('godmode') else "[dim]god mode: pasif[/dim]"
    _aud = "[bold #E06C75]AUDIT[/bold #E06C75]" if modes.is_on('audit') else "[dim]audit: pasif[/dim]"
    _tmp = "[bold #6C7086]TEMP[/bold #6C7086]" if modes.is_on('temp') else "[dim]temp: pasif[/dim]"
    _spd = "[bold #98C379]SPEED[/bold #98C379]" if modes.is_on('speed') else "[dim]speed: pasif[/dim]"
    console.print(f"    ⚡ {_god}")
    console.print(f"    🔍 {_aud}")
    console.print(f"    💭 {_tmp}")
    console.print(f"    🏎️  {_spd}")
    console.print("")


async def cmd_speed(app: "DorinaApp", cmd: str) -> None:
    """Toggle speed mode — max 6 tool/tur, 10 tur limit."""
    from core.mode_manager import modes
    from ui.display import print_success, print_error
    modes.toggle('speed')
    if modes.is_on('speed'):
        print_success("SPEED MOD AKTIF - max 6 tool/tur, 10 tur limit")
    else:
        print_error("Speed mod kapandi")


async def cmd_budget(app: "DorinaApp", cmd: str) -> None:
    """Show/set token budget. Asilinca otomatik context compression tetiklenir."""
    from core.mode_manager import modes
    from ui.display import print_success, print_info, console
    parts = cmd.split()
    if len(parts) > 1 and parts[1].isdigit():
        modes.budget = int(parts[1])
        print_success(
            f"Budget: {parts[1]} token. Asildiginda: "
            f"1) LLM yaniti sonrasi uyari verir  "
            f"2) Otomatik context compression baslatir  "
            f"3) Eski turlar ozetlenir, son 2 tur korunur."
        )
    else:
        rem = modes.budget_remaining
        used = modes.budget_used
        budget = modes.budget
        if budget > 0:
            pct = used / budget * 100
            console.print(f"  [bold]Token Budget:[/] {used:,} / {budget:,} (%{pct:.0f})")
            console.print(f"  [dim]Kalan: {rem:,}[/dim]")
            console.print(f"  [dim]Asilinca: uyari + otomatik context compression[/dim]")
        else:
            print_info(f"Kalan budget: limitsiz (0 = limitsiz). /budget <sayi> ile ayarla.")
            console.print(f"  [dim]Asilinca ne olur:[/dim]")
            console.print(f"  [dim]  1. LLM yanitindan sonra uyari mesaji[/dim]")
            console.print(f"  [dim]  2. Otomatik context compression (eski turlar ozetlenir)[/dim]")
            console.print(f"  [dim]  3. Agent calismaya devam eder, budget yenilenmez[/dim]")
            console.print(f"  [dim]  4. /budget <sayi> ile sifirla[/dim]")


async def cmd_personality(app: "DorinaApp", cmd: str) -> None:
    """Show/set personality."""
    from ui.display import console
    console.print("[dim]Personality simdilik devre disi[/dim]")
