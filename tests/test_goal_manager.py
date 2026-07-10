"""Tests for GoalManager (orchestrator/goal_manager.py).

Tests are fully unit-test isolated: no background tasks run, no SubAgents
are spawned, no task_manager is needed.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_goal_manager():
    """Fresh GoalManager per test."""
    from orchestrator.goal_manager import GoalManager
    gm = GoalManager()
    yield gm
    gm._goals.clear()


@pytest.fixture(autouse=True)
def _mock_event_bus():
    """Prevent event bus side effects."""
    with patch("orchestrator.goal_manager.bus") as mock:
        yield mock


# ── Test: Goal creation ────────────────────────────────────────────────────


class TestGoalCreate:
    """Goal olusturma."""

    def test_create_goal_returns_id(self, fresh_goal_manager):
        """Goal olusturunca 12 karakterlik ID donmeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test goal", "run the tests")
        assert len(goal_id) == 12
        assert goal_id in gm._goals

    def test_create_goal_stores_data(self, fresh_goal_manager):
        """Goal verileri dogru saklanmali."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("my goal", "description here")
        goal = gm._goals[goal_id]
        assert goal.name == "my goal"
        assert goal.description == "description here"
        assert goal.status == "pending"

    def test_create_goal_publishes_event(self, fresh_goal_manager):
        """Goal olusturunca event yayinlanmali."""
        from orchestrator.goal_manager import bus
        gm = fresh_goal_manager
        gm.create_goal("test")
        bus.publish.assert_called_once()
        args, _ = bus.publish.call_args
        assert args[0] == "goal:created"

    def test_create_multiple_goals(self, fresh_goal_manager):
        """Birden fazla goal olusturulabilmeli."""
        gm = fresh_goal_manager
        id1 = gm.create_goal("first")
        id2 = gm.create_goal("second")
        assert id1 != id2
        assert len(gm._goals) == 2


# ── Test: Goal start ──────────────────────────────────────────────────────


class TestGoalStart:
    """Goal baslatma."""

    @pytest.mark.asyncio
    async def test_start_pending_goal(self, fresh_goal_manager):
        """pending durumundaki goal baslatilabilmeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test", "do something")

        with patch("tools.delegate.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="done")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 3
            mock_sa.return_value.error = ""

            result = await gm.start_goal(goal_id)

        parsed = json.loads(result)
        assert parsed["status"] == "running"
        assert parsed["goal_id"] == goal_id
        assert gm._goals[goal_id].status == "running"

    @pytest.mark.asyncio
    async def test_start_nonexistent_goal(self, fresh_goal_manager):
        """Var olmayan goal baslatilamamali."""
        gm = fresh_goal_manager
        result = await gm.start_goal("nonexistent")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_start_already_running_goal(self, fresh_goal_manager):
        """Halihazirda calisan goal tekrar baslatilamamali."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test", "do it")

        with patch("tools.delegate.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="done")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 0
            mock_sa.return_value.error = ""

            await gm.start_goal(goal_id)
            result2 = await gm.start_goal(goal_id)

        parsed = json.loads(result2)
        assert "error" in parsed


# ── Test: Goal cancel ──────────────────────────────────────────────────────


class TestGoalCancel:
    """Goal iptal etme."""

    def test_cancel_pending_goal(self, fresh_goal_manager):
        """pending goal iptal edilebilmeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        result = gm.cancel_goal(goal_id)
        assert result is True
        assert gm._goals[goal_id].status == "cancelled"

    def test_cancel_running_goal(self, fresh_goal_manager):
        """running goal iptal edilebilmeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        gm._goals[goal_id].status = "running"
        result = gm.cancel_goal(goal_id)
        assert result is True

    def test_cancel_completed_goal_fails(self, fresh_goal_manager):
        """tamamlanmis goal iptal edilememeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        gm._goals[goal_id].status = "completed"
        result = gm.cancel_goal(goal_id)
        assert result is False

    def test_cancel_nonexistent_goal(self, fresh_goal_manager):
        """var olmayan goal iptal edilememeli."""
        gm = fresh_goal_manager
        result = gm.cancel_goal("nonexistent")
        assert result is False

    def test_cancel_with_short_id(self, fresh_goal_manager):
        """Kisa ID ile goal iptal edilebilmeli."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        short_id = goal_id[:8]
        result = gm.cancel_goal(short_id)
        assert result is True

    def test_cancel_publishes_event(self, fresh_goal_manager):
        """Goal iptalinde event yayinlanmali."""
        from orchestrator.goal_manager import bus
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        gm.cancel_goal(goal_id)
        # publish called twice: create + cancel
        assert bus.publish.call_count >= 2
        cancel_call = bus.publish.call_args_list[-1]
        assert cancel_call[0][0] == "goal:cancelled"


# ── Test: Goal listing ─────────────────────────────────────────────────────


class TestGoalList:
    """Goal listeleme."""

    def test_list_goals_empty(self, fresh_goal_manager):
        """Hic goal yokken bos liste donmeli."""
        gm = fresh_goal_manager
        assert gm.list_goals() == []

    def test_list_goals_returns_all(self, fresh_goal_manager):
        """Tum goal'leri listele."""
        gm = fresh_goal_manager
        gm.create_goal("first")
        gm.create_goal("second")
        goals = gm.list_goals()
        assert len(goals) == 2

    def test_list_goals_filter_by_status(self, fresh_goal_manager):
        """Status filtresi ile listele."""
        gm = fresh_goal_manager
        g1 = gm.create_goal("running")
        g2 = gm.create_goal("pending")
        gm._goals[g1].status = "running"
        running = gm.list_goals(status_filter="running")
        pending = gm.list_goals(status_filter="pending")
        assert len(running) == 1
        assert len(pending) == 1
        assert running[0]["name"] == "running"
        assert pending[0]["name"] == "pending"

    def test_list_goals_contains_expected_fields(self, fresh_goal_manager):
        """Listelenen goal'lerde zorunlu alanlar olmali."""
        gm = fresh_goal_manager
        gm.create_goal("test", "desc")
        goals = gm.list_goals()
        g = goals[0]
        assert "id" in g
        assert "name" in g
        assert "status" in g
        assert "elapsed" in g
        assert "created_at" in g

    def test_list_goals_newest_first(self, fresh_goal_manager):
        """En yeni goal ilk sirada gelmeli."""
        gm = fresh_goal_manager
        import time
        g1 = gm.create_goal("older")
        time.sleep(0.01)
        g2 = gm.create_goal("newer")
        goals = gm.list_goals()
        assert goals[0]["name"] == "newer"
        assert goals[1]["name"] == "older"


# ── Test: Goal get ─────────────────────────────────────────────────────────


class TestGoalGet:
    """Goal detayi getirme."""

    def test_get_goal_by_full_id(self, fresh_goal_manager):
        """Tam ID ile goal getir."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test", "desc")
        goal = gm.get_goal(goal_id)
        assert goal is not None
        assert goal.name == "test"
        assert goal.description == "desc"

    def test_get_goal_by_short_id(self, fresh_goal_manager):
        """Kisa ID ile goal getir."""
        gm = fresh_goal_manager
        goal_id = gm.create_goal("test")
        goal = gm.get_goal(goal_id[:8])
        assert goal is not None

    def test_get_goal_nonexistent(self, fresh_goal_manager):
        """Var olmayan goal None donmeli."""
        gm = fresh_goal_manager
        assert gm.get_goal("xyz") is None


# ── Test: Running count ────────────────────────────────────────────────────


class TestRunningCount:
    """Aktif goal sayisi."""

    def test_running_count_zero(self, fresh_goal_manager):
        """Hic running goal yokken 0 donmeli."""
        gm = fresh_goal_manager
        assert gm.running_count() == 0

    def test_running_count_with_mixed(self, fresh_goal_manager):
        """Sadece running goal'leri saymali."""
        gm = fresh_goal_manager
        g1 = gm.create_goal("running1")
        g2 = gm.create_goal("running2")
        g3 = gm.create_goal("pending")
        gm._goals[g1].status = "running"
        gm._goals[g2].status = "running"
        assert gm.running_count() == 2

    def test_running_count_after_cancel(self, fresh_goal_manager):
        """Iptal edilen goal sayilmamali."""
        gm = fresh_goal_manager
        g1 = gm.create_goal("running")
        gm._goals[g1].status = "running"
        assert gm.running_count() == 1
        gm.cancel_goal(g1)
        assert gm.running_count() == 0


# ── Test: Goal elapsed ─────────────────────────────────────────────────────


class TestGoalElapsed:
    """Goal sure formatlama."""

    def test_elapsed_seconds(self, fresh_goal_manager):
        """60 saniyeden kisa sureler 'Xs' formatinda olmali."""
        gm = fresh_goal_manager
        gid = gm.create_goal("test")
        goal = gm._goals[gid]
        elapsed = goal.elapsed
        assert "s" in elapsed

    def test_elapsed_empty(self, fresh_goal_manager):
        """Baslangicta elapsed sifir olmamali (en az 0s gosterebilir)."""
        gm = fresh_goal_manager
        gid = gm.create_goal("test")
        goal = gm._goals[gid]
        assert goal.elapsed is not None

    def test_short_id_property(self, fresh_goal_manager):
        """short_id ilk 8 karakteri donmeli."""
        gm = fresh_goal_manager
        gid = gm.create_goal("test")
        goal = gm._goals[gid]
        assert goal.short_id == gid[:8]
