"""Komut onay sistemi — tehlikeli işlemler için.

always_allow:   Bu listedeki tool'lar direkt geçer, onay sorulmaz.
ask_always:     Bu listedeki tool'lar her çağrıldığında onay ister.
Diğer tool'lar: mode'a göre (smart/manual/off) değerlendirilir.
"""

from __future__ import annotations
from tools.security import is_destructive
from core.config import settings


class Approval:
    """Tehlikeli işlemler için onay mekanizması."""

    MODE_SMART = "smart"
    MODE_MANUAL = "manual"
    MODE_OFF = "off"

    def __init__(self, mode: str | None = None):
        self.mode = mode or settings.tools.approval_mode
        # Config'den approval listelerini oku
        self.always_allow: list[str] = list(settings.security.always_allow or [])
        self.ask_always: list[str] = list(settings.security.ask_always or [])

    def needs_approval(self, tool_name: str, arguments: dict) -> bool:
        """Bu işlem onay gerektiriyor mu?"""
        if self.mode == self.MODE_OFF:
            return False

        # always_allow: skip directly, no approval required
        if tool_name in self.always_allow:
            return False

        # ask_always: her zaman onay iste
        if tool_name in self.ask_always:
            return True

        # Terminal commands
        if tool_name == "terminal":
            command = arguments.get("command", "")
            if is_destructive(command):
                return True

        # Dosya silme
        if tool_name in ("delete_file", "rm"):
            return True

        # Smart mode'da daha az onay
        if self.mode == self.MODE_SMART:
            return False  # Sadece çok riskli olanlar onaylanır

        return True

    def approve(self, tool_name: str, arguments: dict) -> bool:
        """Kullanıcıya sor, onayla mı?"""
        if not self.needs_approval(tool_name, arguments):
            return True

        print(f"\n[onay] {tool_name} çağrılacak: {arguments}")
        resp = input("Onaylıyor musun? (E/h): ").strip().lower()
        return resp in ("", "e", "evet", "y", "yes")

    def reload_from_config(self):
        """Config dosyasını yeniden oku (hot-reload)."""
        from core.config import Settings
        fresh = Settings.load()
        self.mode = fresh.tools.approval_mode
        self.always_allow = list(fresh.security.always_allow or [])
        self.ask_always = list(fresh.security.ask_always or [])


approval = Approval()


def _approval_hook(tool_name: str, arguments: dict) -> bool:
    """Pre-execution hook: tool cagrilmadan once onay al."""
    return approval.approve(tool_name, arguments)


# Kendini pipeline'a kaydet (lazy import)
def _register_approval_hook():
    try:
        from hooks.lifecycle import pipeline
        pipeline.register("pre_execution", _approval_hook)
    except ImportError:
        pass  # pipeline henuz hazir degilse sessizce gec


_register_approval_hook()
