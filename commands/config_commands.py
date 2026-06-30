"""Configuration commands: /model, /godmode, /audit, /personality."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from main import DorinaApp


async def cmd_model(app: "DorinaApp", cmd: str) -> None:
    """Switch model or run setup wizard::

        /model openai/gpt-4o
        /model                     # runs setup wizard
    """
    from core.config import settings
    from ui.display import print_success, print_error
    from ui.status_bar import status

    parts = cmd.split()
    if len(parts) > 1:
        model_str = parts[1].strip()
        if "/" in model_str:
            provider, model_name = model_str.split("/", 1)
            settings.model.provider = provider
            settings.model.default = model_str
            settings.save()
            status.model = model_str
            print_success(f"Model değiştirildi: {model_str}")
        else:
            print_error("Hatalı format. Örnek: /model openai/gpt-4o")
    else:
        from ui.setup_wizard import run_setup_wizard

        await run_setup_wizard()
        print_success("Model güncellendi")


async def cmd_godmode(app: "DorinaApp", cmd: str) -> None:
    """Toggle god mode (removes restrictions, requests sudo password)."""
    from core import constants
    import soul.personality as _sp
    from core.config import settings
    from ui.display import console, print_success, print_info
    from ui.repl import set_style

    if not hasattr(settings.model, "godmode"):
        settings.model.godmode = False
    settings.model.godmode = not settings.model.godmode
    godmode_active = settings.model.godmode
    _sp.GODMODE = godmode_active

    import os

    if godmode_active:
        os.system("clear")
        set_style(True)
        settings.security.block_destructive_commands = False
        constants.MAX_TURNS = 200
        constants.MAX_TOOL_CALLS_PER_TURN = 999
        banner = (
            "╔══════════════════════════════╗\n"
            "║      ⚡ GOD MODE AKTIF ⚡     ║\n"
            "║   Tüm kısıtlamalar kalktı   ║\n"
            "╚══════════════════════════════╝"
        )
        console.print(banner, style="bold red")
        from prompt_toolkit import PromptSession

        session = PromptSession()
        pwd = await session.prompt_async(
            "Sudo şifreniz (RAM'de tutulacak, boş geçmek için Enter): ",
            is_password=True,
        )
        if pwd:
            _sp.SUDO_PASSWORD = pwd
    else:
        _sp.SUDO_PASSWORD = None
        os.system("clear")
        set_style(False)
        settings.security.block_destructive_commands = True
        constants.MAX_TURNS = 50
        constants.MAX_TOOL_CALLS_PER_TURN = 30
        print_success("God Mode KAPALI")


async def cmd_audit(app: "DorinaApp", cmd: str) -> None:
    """Toggle audit mode (stricter code scrutiny)."""
    import soul.personality as _sp
    from ui.repl import set_style
    from ui.display import console, print_success, print_info

    import os

    _sp.AUDIT_MODE = not _sp.AUDIT_MODE
    set_style("audit" if _sp.AUDIT_MODE else False)
    os.system("clear")
    if _sp.AUDIT_MODE:
        banner = (
            "╔══════════════════════════════╗\n"
            "║      🔍 AUDIT MOD ACIK       ║\n"
            "║    Tüm kodlar mercek altında ║\n"
            "╚══════════════════════════════╝"
        )
        console.print(banner, style="bold #E06C75")
        print_info(
            "Örnek komutlar:\n"
            "  > self_check ile bu projeyi detaylıca tara\n"
            "  > lsp_diagnostics <dosya> ile hataları listele\n"
            "  > diff_history ile son değişiklikleri incele"
        )
    else:
        print_success("Audit Mod KAPALI")


async def cmd_personality(app: "DorinaApp", cmd: str) -> None:
    """Show current personality configuration."""
    from ui.display import console
    from soul.personality import soul
    from core.constants import DORINA_HOME

    spath = DORINA_HOME / "SOUL.md"
    if spath.exists():
        console.print(spath.read_text())
    else:
        console.print(f"[#D4622A]Kişilik:[/#D4622A] {soul.system_prompt[:200]}")
