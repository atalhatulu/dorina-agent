"""Tests for ModeManager."""
import pytest
import time
from core.mode_manager import ModeManager, modes


class TestModeManager:
    def test_singleton(self):
        m1 = ModeManager()
        m2 = ModeManager()
        assert m1 is m2

    def test_toggle(self):
        modes.reset()
        assert not modes.is_on("godmode")
        modes.toggle("godmode")
        assert modes.is_on("godmode")
        modes.toggle("godmode")
        assert not modes.is_on("godmode")

    def test_set(self):
        from core.constants import set_language
        set_language("tr")
        modes.reset()
        r = modes.set("godmode", True)
        assert "Aktif" in r
        assert modes.is_on("godmode")

    def test_reset(self):
        modes.set("godmode", True)
        modes.set("audit", True)
        modes.reset()
        assert not modes.is_on("godmode")
        assert not modes.is_on("audit")

    def test_godmode_timeout(self):
        modes.reset()
        modes.set("godmode", True, timeout=0.01)  # 10ms timeout
        time.sleep(0.02)
        remaining = modes.godmode_remaining
        assert remaining == 0  # sure doldu, otomatik kapandi
        assert not modes.is_on("godmode")

    def test_active_list(self):
        modes.reset()
        assert modes.active == []
        modes.set("godmode", True)
        assert "godmode" in modes.active
        modes.set("audit", True)
        assert "audit" in modes.active
        modes.reset()
        assert modes.active == []

    def test_budget(self):
        modes.reset()
        assert modes.budget_remaining == -1  # limitsiz
        modes.budget = 5000
        assert modes.budget == 5000
        assert modes.budget_remaining == 5000
        hit = modes.budget_hit(3000)
        assert not hit
        assert modes.budget_remaining == 2000
        hit = modes.budget_hit(2000)
        assert hit  # budget asildi
        assert modes.budget_remaining == 0

    def test_summary(self):
        modes.reset()
        assert modes.summary() == "normal"
        modes.set("godmode", True)
        s = modes.summary()
        assert "GODMODE" in s
        modes.set("speed", True)
        s = modes.summary()
        assert "GODMODE" in s
        assert "SPEED" in s

    def test_unknown_mod(self):
        from core.constants import set_language
        set_language("tr")
        r = modes.set("olmayan_mod", True)
        assert "Bilinmeyen" in r
        r = modes.toggle("olmayan_mod")
        assert "Bilinmeyen" in r
