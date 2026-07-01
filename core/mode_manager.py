"""ModeManager — tum modlari tek merkezde yoneten singleton.

Modlar:
- godmode: kisitlama yok, sudo parola otomatik
- audit: denetim modu, sadece okuma tool'lari
- temp: kayitsiz sohbet
- speed: hizli mod, kisitli tool/turn
- strict: yazma oncesi onay
- silent: tool ciktilarini gosterme
"""

from __future__ import annotations
import time
from typing import Any
from core.event_bus import bus


class ModeManager:
    """Tek noktadan mod yonetimi. Singleton."""

    _instance: ModeManager | None = None

    def __new__(cls) -> ModeManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._modes: dict[str, dict[str, Any]] = {
            "godmode": {"active": False, "started_at": 0.0, "timeout": 1800},
            "audit": {"active": False, "red_blue": False},
            "temp": {"active": False},
            "speed": {"active": False, "max_tools": 6, "max_turns": 10, "top_k": 5},
            "strict": {"active": False},
            "silent": {"active": False},
            "deep": {"active": False, "max_tools": 20, "max_turns": 100},
        }
        self._profile = ""  # aktif kullanici profili
        self._budget: int = 0  # token budget (0 = limitsiz)
        self._budget_used: int = 0
        self._budget_warned: bool = False  # her budget periyodunda bir kere uyar

    # ── Temel API ────────────────────────────────────────────

    @property
    def active(self) -> list[str]:
        return [k for k, v in self._modes.items() if v["active"]]

    def get(self, name: str) -> dict[str, Any] | None:
        return self._modes.get(name)

    def is_on(self, name: str) -> bool:
        m = self._modes.get(name)
        return m is not None and m["active"]

    def set(self, name: str, active: bool, **kwargs) -> str:
        """Mod ac/kapa. Event bus'a bildirim gonderir."""
        m = self._modes.get(name)
        if m is None:
            return f"Bilinmeyen mod: {name}"

        old = m["active"]
        m["active"] = active
        if kwargs:
            m.update(kwargs)
        if active and name == "godmode":
            m["started_at"] = time.time()

        # Event yayinla
        bus.publish("mode_change", mod=name, old=old, new=active)
        return f"{'Aktif' if active else 'Pasif'}: {name}"

    def toggle(self, name: str) -> str:
        m = self._modes.get(name)
        if m is None:
            return f"Bilinmeyen mod: {name}"
        return self.set(name, not m["active"])

    def reset(self):
        """Tum modlari kapat, temiz baslangic."""
        for name, m in self._modes.items():
            m["active"] = False
            if name == "godmode":
                m["started_at"] = 0.0
                m["timeout"] = 1800
        self._budget = 0
        self._budget_used = 0
        self._budget_warned = False

    # ── Godmode timeout ─────────────────────────────────────

    @property
    def godmode_remaining(self) -> int:
        m = self._modes.get("godmode")
        if not m or not m["active"]:
            return 0
        elapsed = time.time() - m.get("started_at", 0)
        remaining = int(m.get("timeout", 1800) - elapsed)
        if remaining <= 0:
            self.set("godmode", False)
            bus.publish("godmode_timeout")
            return 0
        return remaining

    # ── /budget ───────────────────────────────────────────────

    @property
    def budget(self) -> int:
        return self._budget

    @budget.setter
    def budget(self, value: int):
        self._budget = max(0, value)
        self._budget_used = 0
        self._budget_warned = False

    def budget_hit(self, tokens: int) -> bool:
        """Token harcadiktan sonra budget asildi mi? Her budget periyodunda bir kere True doner."""
        if self._budget <= 0:
            return False
        self._budget_used += tokens
        if self._budget_used >= self._budget and not self._budget_warned:
            self._budget_warned = True
            return True
        return False

    @property
    def budget_used(self) -> int:
        return self._budget_used

    @property
    def budget_remaining(self) -> int:
        if self._budget <= 0:
            return -1  # limitsiz
        return max(0, self._budget - self._budget_used)

    # ── Profile ──────────────────────────────────────────────

    def set_profile(self, name: str):
        self._profile = name

    @property
    def profile(self) -> str:
        return self._profile

    # ── String goruntuleme ─────────────────────────────────

    def summary(self) -> str:
        parts = []
        if self.is_on("godmode"):
            rem = self.godmode_remaining
            parts.append(f"GODMODE ({rem // 60}:{rem % 60:02d})")
        if self.is_on("audit"):
            parts.append("AUDIT")
        if self.is_on("temp"):
            parts.append("TEMP")
        if self.is_on("speed"):
            parts.append("SPEED")
        if self.is_on("strict"):
            parts.append("STRICT")
        if self.is_on("silent"):
            parts.append("SILENT")
        if self.is_on("deep"):
            parts.append("DEEP")
        if self._budget > 0:
            parts.append(f"BUDGET:{self._budget_used}/{self._budget}")
        return " | ".join(parts) if parts else "normal"


# Module-level singleton
modes = ModeManager()
