"""Tests for the real multi-agent crew — SubAgent delegation backend.

These tests assert that crew methods wire to the real `tools.delegate.SubAgent`
(patched) rather than the old facade that merely returned canned status strings.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def fresh_crew():
    from agents.crew import AgentCrew
    c = AgentCrew()
    yield c
    c.clear()


# ── Member management ────────────────────────────────────────────────────────

class TestMemberMgmt:
    def test_add_member(self, fresh_crew):
        fresh_crew.add_member("researcher", "find X")
        assert fresh_crew.member_count() == 1

    def test_add_agent_alias(self, fresh_crew):
        fresh_crew.add_agent("writer", "write it")
        assert fresh_crew.member_count() == 1

    def test_add_requires_goal(self, fresh_crew):
        fresh_crew.add_member("researcher", "")
        assert fresh_crew.member_count() == 0

    def test_clear(self, fresh_crew):
        fresh_crew.add_agent("writer", "w")
        fresh_crew.clear()
        assert fresh_crew.member_count() == 0


# ── Toolset mapping per role ─────────────────────────────────────────────────

class TestRoleToolsets:
    def test_researcher_maps_to_web(self, fresh_crew):
        assert fresh_crew._toolsets_for("researcher") == ["file", "web"]

    def test_reviewer_maps_to_file_terminal(self, fresh_crew):
        assert fresh_crew._toolsets_for("reviewer") == ["file", "terminal"]

    def test_unknown_role_falls_back(self, fresh_crew):
        assert fresh_crew._toolsets_for("random_role") == ["file", "web", "terminal"]


# ── Real SubAgent delegation ─────────────────────────────────────────────────

class TestDelegation:
    @pytest.mark.asyncio
    async def test_run_crew_delegates_to_subagent(self, fresh_crew):
        """Sequential crew spawns a real SubAgent per member with role-tuned toolsets."""
        fresh_crew.add_agent("researcher", "find X")
        fresh_crew.add_agent("reviewer", "check it")
        with patch("agents.crew.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="RESULT")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 3
            mock_sa.return_value.error = ""
            out = await fresh_crew.run_crew("the shared task")
        parsed = json.loads(out)
        assert parsed["status"] == "completed"
        assert len(parsed["members"]) == 2
        # SubAgent constructed with the right toolsets for each role
        toolsets = {c.kwargs["toolsets"][-1] for c in mock_sa.call_args_list}
        assert {"web", "terminal"} == toolsets
        # real result flows back, not a canned status string
        assert parsed["members"][0]["result"] == "RESULT"

    @pytest.mark.asyncio
    async def test_run_crew_parallel(self, fresh_crew):
        fresh_crew.add_agent("researcher", "r")
        fresh_crew.add_agent("writer", "w")
        with patch("agents.crew.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(side_effect=["P1", "P2"])
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 2
            mock_sa.return_value.error = ""
            out = await fresh_crew.run_crew_parallel("task")
        parsed = json.loads(out)
        assert len(parsed["members"]) == 2
        results = [m["result"] for m in parsed["members"]]
        assert set(results) == {"P1", "P2"}

    @pytest.mark.asyncio
    async def test_fork_subagent_is_real(self, fresh_crew):
        """fork_subagent returns the actual SubAgent result, not a simulation."""
        with patch("agents.crew.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="FORK_ACTUAL")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 9
            mock_sa.return_value.error = ""
            out = await fresh_crew.fork_subagent("summarize X", tools=["file"])
        parsed = json.loads(out)
        assert parsed["status"] == "completed"
        assert parsed["result"] == "FORK_ACTUAL"
        assert parsed["tools_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_crew_returns_message(self, fresh_crew):
        out = await fresh_crew.run_crew("task")
        parsed = json.loads(out)
        assert parsed["status"] == "empty"

    @pytest.mark.asyncio
    async def test_fork_tracks_record(self, fresh_crew):
        with patch("agents.crew.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="X")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 1
            mock_sa.return_value.error = ""
            await fresh_crew.fork_subagent("goal")
        assert len(fresh_crew.list_forks()) == 1


# ── crew_run / crew_fork tools ───────────────────────────────────────────────

class TestCrewTools:
    def test_crew_run_registered(self):
        from tools.builtin.crew_tools import crew_run_tool
        assert callable(crew_run_tool)

    def test_crew_fork_registered(self):
        from tools.builtin.crew_tools import crew_fork_tool
        assert callable(crew_fork_tool)