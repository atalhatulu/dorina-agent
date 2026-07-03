"""ModeManager — single point of control for all modes.

Modes:
- godmode: no restrictions, sudo password auto-filled
- audit: audit mode, read-only tools only
- temp: off-the-record chat
- speed: fast mode, limited tools/turn
- strict: approval required before writes
- silent: hide tool outputs
"""

from __future__ import annotations
import time
from typing import Any
from core.constants import get_language
from core.event_bus import bus


class ModeManager:
    """Centralized mode management. Singleton."""

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
        self._profile = ""  # active user profile
        self._budget: int = 0  # token budget (0 = unlimited)
        self._budget_used: int = 0
        self._budget_warned: bool = False  # one warning per budget period

    # ── Core API ─────────────────────────────────────────────

    @property
    def active(self) -> list[str]:
        return [k for k, v in self._modes.items() if v["active"]]

    def get(self, name: str) -> dict[str, Any] | None:
        return self._modes.get(name)

    def is_on(self, name: str) -> bool:
        m = self._modes.get(name)
        return m is not None and m["active"]

    def set(self, name: str, active: bool, **kwargs) -> str:
        """Activate/deactivate a mode. Publishes mode_change event."""
        m = self._modes.get(name)
        if m is None:
            _lang = get_language()
            return f"{'Bilinmeyen mod' if _lang == 'tr' else 'Unknown mode'}: {name}"

        old = m["active"]
        m["active"] = active
        if kwargs:
            m.update(kwargs)
        if active and name == "godmode":
            m["started_at"] = time.time()

        # Publish event
        bus.publish("mode_change", mod=name, old=old, new=active)
        _lang = get_language()
        _active_str = "Aktif" if _lang == "tr" else "Active"
        _passive_str = "Pasif" if _lang == "tr" else "Inactive"
        return f"{_active_str if active else _passive_str}: {name}"

    def toggle(self, name: str) -> str:
        m = self._modes.get(name)
        if m is None:
            _lang = get_language()
            return f"{'Bilinmeyen mod' if _lang == 'tr' else 'Unknown mode'}: {name}"
        return self.set(name, not m["active"])

    def reset(self):
        """Reset all modes to inactive, clean start."""
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
        """Check if budget was exceeded after spending tokens. Returns True once per budget period."""
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
            return -1  # unlimited
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
