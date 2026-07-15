"""Config commands: /model, /godmode, /audit, /personality.

/model command:
  /model               → interactive provider selector + model picker
  /model key <p> <k>   → set API key for provider
  /model switch <p>    → quick switch to provider's first model
  /model list          → show all providers with key status
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from core.constants import t

if TYPE_CHECKING:
    from app import DorinaApp


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
            print_success(t("model_current", model=f"{provider}/{model}"))
        else:
            # Different provider: check API key
            if keys.has_key(provider):
                # Has key: ask for model
                model = await select_model(provider)
                if model is None:
                    return
                keys.switch_to(provider, model)
                print_success(t("model_switched", model=f"{provider}/{model}"))
            else:
                # No key: prompt for it
                print_info(t("model_key_required", provider=provider))
                console.print(f"  /model key {provider} <api_key>")
                return

    elif len(parts) >= 4 and parts[1] == "key":
        # ── /model key <provider> <key> ──
        prov = parts[2]
        new_key = parts[3].strip()
        keys.save_key(prov, new_key)
        print_success(t("model_key_updated", provider=prov, len=len(new_key)))

    elif len(parts) >= 3 and parts[1] == "switch":
        # ── /model switch <provider> ──
        prov = parts[2]
        if prov in PROVIDERS:
            models = PROVIDERS[prov].get("models", [])
            if models:
                keys.switch_to(prov, models[0])
                from core.model_utils import build_model_string
                model_str = build_model_string(prov, models[0])
                print_success(t("model_switched", model=model_str))
            else:
                print_error(t("model_no_models", provider=prov))
        else:
            print_error(t("model_unknown_provider", provider=prov))

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
            key_s = f"[green]{t('provider_key_present')}[/]" if has else f"[dim]{t('provider_key_missing')}[/dim]"
            masked = keys.get_key(name)[:10] + "..." if has and len(keys.get_key(name)) > 10 else ""
            console.print(f"  {dot} {name:14s}  {key_s}  [dim]{masked}[/dim]")
        console.print("")
        console.print("  [dim]/model key <provider> <api_key>  /model switch <provider>[/dim]")
        console.print("")

    else:
        print_error(t("model_usage"))


async def cmd_godmode(app: "DorinaApp", cmd: str) -> None:
    """Toggle god mode — unlimited, all security restrictions lifted."""
    from ui.display import print_success, print_error
    from ui.repl import set_style
    from core.config import settings
    from core.mode_manager import modes
    modes.toggle('godmode')
    settings.model.godmode = modes.is_on('godmode')
    settings.save()
    if modes.is_on('godmode'):
        set_style('godmode')
        print_success(t("godmode_activated"))
    else:
        if modes.is_on('audit'):
            set_style('audit')
        elif modes.is_on('temp'):
            set_style('temp')
        else:
            set_style('')
        print_error(t("godmode_deactivated"))


async def cmd_audit(app: "DorinaApp", cmd: str) -> None:
    """Toggle audit mode."""
    from ui.display import print_success, print_error
    from ui.repl import set_style
    from core.mode_manager import modes
    modes.toggle('audit')
    if modes.is_on('audit'):
        set_style('audit')
        print_success(t("audit_activated"))
    else:
        if modes.is_on('godmode'):
            set_style('godmode')
        elif modes.is_on('temp'):
            set_style('temp')
        else:
            set_style('')
        print_error(t("audit_deactivated"))


async def cmd_auto(app: "DorinaApp", cmd: str) -> None:
    """Toggle auto mode — autonomous continuous operation with extended timeouts and iterations."""
    from ui.display import print_success, print_error
    from core.mode_manager import modes
    modes.toggle('auto')
    
    _lang = get_language()
    _active = "Otonom mod aktif: Zaman aşımı ve döngü limitleri uzatıldı." if _lang == 'tr' else "Auto mode active: Extended timeouts and iteration limits."
    _inactive = "Otonom mod kapatıldı." if _lang == 'tr' else "Auto mode deactivated."
    
    if modes.is_on('auto'):
        print_success(_active)
    else:
        print_error(_inactive)



async def cmd_mods(app: "DorinaApp", cmd: str) -> None:
    """Show active modes: godmode, audit, temp, speed, strict, silent, deep."""
    from core.mode_manager import modes
    from ui.display import console

    console.print("")
    console.print(f"  [bold]{t('model_active_modes')}[/bold]")
    console.print("  ─────────────")
    _god = f"[bold #ff3333]{t('model_god_active')}[/bold #ff3333]" if modes.is_on('godmode') else f"[dim]{t('model_god_inactive')}[/dim]"
    _aud = f"[bold #E06C75]{t('model_audit_active')}[/bold #E06C75]" if modes.is_on('audit') else f"[dim]{t('model_audit_inactive')}[/dim]"
    _tmp = f"[bold #6C7086]{t('model_temp_active')}[/bold #6C7086]" if modes.is_on('temp') else f"[dim]{t('model_temp_inactive')}[/dim]"
    _spd = f"[bold #98C379]{t('model_speed_active')}[/bold #98C379]" if modes.is_on('speed') else f"[dim]{t('model_speed_inactive')}[/dim]"
    
    _lang = get_language()
    _auto_active = "Otonom: Aktif" if _lang == 'tr' else "Auto: Active"
    _auto_inactive = "Otonom: Pasif" if _lang == 'tr' else "Auto: Inactive"
    _aut = f"[bold #E5C07B]{_auto_active}[/bold #E5C07B]" if modes.is_on('auto') else f"[dim]{_auto_inactive}[/dim]"

    console.print(f"    ⚡ {_god}")
    console.print(f"    🔍 {_aud}")
    console.print(f"    💭 {_tmp}")
    console.print(f"    🏎️  {_spd}")
    console.print(f"    🤖 {_aut}")
    console.print("")


async def cmd_speed(app: "DorinaApp", cmd: str) -> None:
    """Toggle speed mode — max 6 tools/turn, 10 turn limit."""
    from core.mode_manager import modes
    from ui.display import print_success, print_error
    modes.toggle('speed')
    if modes.is_on('speed'):
        print_success(t("speed_activated"))
    else:
        print_error(t("speed_deactivated"))


async def cmd_budget(app: "DorinaApp", cmd: str) -> None:
    """Show/set token budget. Triggers auto context compression on overflow."""
    from core.mode_manager import modes
    from ui.display import print_success, print_info, console
    parts = cmd.split()
    if len(parts) > 1 and parts[1].isdigit():
        modes.budget = int(parts[1])
        print_success(t("budget_set", budget=parts[1]))
    else:
        rem = modes.budget_remaining
        used = modes.budget_used
        budget = modes.budget
        if budget > 0:
            pct = used / budget * 100
            console.print(t("budget_status", used=used, total=budget, pct=pct))
            console.print(f"  [dim]{t('budget_remaining', remaining=rem)}[/dim]")
            console.print(f"  [dim]{t('budget_overflow_hint')}[/dim]")
        else:
            print_info(t("budget_unlimited"))
            console.print(f"  [dim]{t('budget_overflow_detail_1')}[/dim]")
            console.print(f"  [dim]{t('budget_overflow_detail_2')}[/dim]")
            console.print(f"  [dim]{t('budget_overflow_detail_3')}[/dim]")
            console.print(f"  [dim]{t('budget_overflow_detail_4')}[/dim]")


async def cmd_personality(app: "DorinaApp", cmd: str) -> None:
    """Show/set personality."""
    from ui.display import console
    console.print(f"[dim]{t('personality_disabled')}[/dim]")
