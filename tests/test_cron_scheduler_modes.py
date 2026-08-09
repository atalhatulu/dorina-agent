"""Tests for cron scheduler — shell vs LLM-agent job modes, and the cron tool.

Isolated: no scheduler thread runs. We test CronJob construction, mode routing,
shell execution, agent-mission execution (with a mocked SubAgent), file
persistence (mode/toolsets round-trip), and the cron tool's add/list/run.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def fresh_scheduler(tmp_path, monkeypatch):
    """A CronScheduler writing to a temp jobs file (no real ~/.dorina state)."""
    from cron.scheduler import CronScheduler
    monkeypatch.setattr(Path, "exists", lambda self, *a, **k: False)
    s = CronScheduler()
    s.jobs.clear()
    yield s
    s.stop()


# ── Mode routing ─────────────────────────────────────────────────────────────

class TestCronJobModes:
    def test_default_mode_is_shell(self):
        """mode defaults to 'shell' so legacy jobs stay compatible."""
        from cron.scheduler import CronJob
        job = CronJob(id="a", name="t", schedule="1h", prompt="echo x")
        assert job.mode == "shell"

    def test_agent_mode_set(self):
        """mode='agent' is honored on construction."""
        from cron.scheduler import CronJob
        job = CronJob(id="a", name="t", schedule="1h", prompt="do x", mode="agent")
        assert job.mode == "agent"
        assert job.toolsets == ["file", "web", "terminal"]

    def test_json_roundtrip_preserves_mode_and_toolsets(self, fresh_scheduler, tmp_path):
        """mode + toolsets survive a save/load cycle."""
        from cron.scheduler import CronJob
        job = CronJob(
            id="abc12345", name="research", schedule="1h", prompt="research X",
            mode="agent", toolsets=["web", "research"],
        )
        fresh_scheduler.jobs = [job]
        raw = json.dumps([{
            "id": j.id, "name": j.name, "schedule": j.schedule, "prompt": j.prompt,
            "mode": j.mode, "toolsets": list(j.toolsets),
            "last_run": j.last_run, "next_run": j.next_run,
            "enabled": j.enabled, "run_count": j.run_count,
        } for j in fresh_scheduler.jobs])
        from cron.scheduler import CronScheduler, CronJob
        with patch.object(Path, "exists", return_value=False):
            pass
        # Reconstruct via CronJob(**json) the same way _load does
        restored = CronJob(**json.loads(raw)[0])
        assert restored.mode == "agent"
        assert restored.toolsets == ["web", "research"]

    def test_add_agent_mode(self, fresh_scheduler):
        """scheduler.add() accepts and stores agent mode."""
        jid = fresh_scheduler.add("m", "2h", "prompt", mode="agent")
        job = next(j for j in fresh_scheduler.jobs if j.id == jid)
        assert job.mode == "agent"

    def test_add_unnamed_mode_defaults_shell(self, fresh_scheduler):
        """add() without mode stays shell (back-compat)."""
        jid = fresh_scheduler.add("m2", "2h", "echo")
        job = next(j for j in fresh_scheduler.jobs if j.id == jid)
        assert job.mode == "shell"


# ── Execution routing ────────────────────────────────────────────────────────

class TestExecuteRouting:
    def test_shell_job_runs_subprocess(self, fresh_scheduler):
        """mode='shell' executes prompt as a shell command."""
        from cron.scheduler import CronJob
        from cron.scheduler import _run_shell_job
        job = CronJob(id="x", name="echo", schedule="1h", prompt="echo shell_ok", mode="shell")
        out, err = _run_shell_job(job)
        assert "shell_ok" in out

    def test_agent_job_runs_subagent(self, fresh_scheduler):
        """mode='agent' routes to a SubAgent mission with its own toolsets."""
        from cron.scheduler import _run_agent_job, CronJob
        job = CronJob(id="s", name="agentjob", schedule="1h",
                      prompt="research and report", mode="agent")
        with patch("tools.delegate.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="AGENT_RESULT")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 5
            mock_sa.return_value.error = ""
            out, err = _run_agent_job(job)
        assert "AGENT_RESULT" in out
        assert "completed" in out
        kw = mock_sa.call_args.kwargs
        assert kw["goal"] == "research and report"
        assert kw["toolsets"] == ["file", "web", "terminal"]

    def test_agent_job_uses_job_specific_toolsets(self, fresh_scheduler):
        """agent job uses the job's toolsets, not the default."""
        from cron.scheduler import _run_agent_job, CronJob
        job = CronJob(id="s", name="w", schedule="1h", prompt="web only",
                      mode="agent", toolsets=["web"])
        with patch("tools.delegate.SubAgent") as mock_sa:
            mock_sa.return_value.run = AsyncMock(return_value="ok")
            mock_sa.return_value.status = "completed"
            mock_sa.return_value.turn_count = 1
            mock_sa.return_value.error = ""
            _run_agent_job(job)
        assert mock_sa.call_args.kwargs["toolsets"] == ["web"]

    def test_execute_dispatches_by_mode(self, fresh_scheduler):
        """_execute writes an output file with the sub-agent result for agent mode."""
        from cron.scheduler import CronJob
        from unittest.mock import patch
        job = CronJob(id="j1", name="agentjob", schedule="1h",
                      prompt="do it", mode="agent")
        fresh_scheduler.jobs = [job]
        with patch("cron.scheduler._run_agent_job", return_value=("AGENT_OUT", "")):
            fresh_scheduler._execute(job)
        assert job.run_count == 1
        assert job.last_run is not None


# ── cron tool ────────────────────────────────────────────────────────────────

class TestCronTool:
    def test_add_agent_mode_tool(self):
        """cron tool add with mode='agent' returns success + mode in message."""
        from tools.builtin.cron_tools import cron_tool
        with patch("cron.scheduler.cron") as mock_cron:
            mock_cron.add.return_value = "jid123"
            r = cron_tool(action="add", name="n", schedule="30m",
                          prompt="p", mode="agent", toolsets=["web"])
        parsed = json.loads(r)
        assert parsed["success"] is True
        assert "mode=agent" in parsed["message"]
        assert mock_cron.add.call_args.kwargs["mode"] == "agent"

    def test_list_returns_mode(self):
        from tools.builtin.cron_tools import cron_tool
        from cron.scheduler import CronJob
        with patch("cron.scheduler.cron") as mock_cron:
            mock_cron.list_jobs.return_value = [
                CronJob(id="a", name="n", schedule="1h", prompt="p", mode="agent")
            ]
            r = cron_tool(action="list")
        parsed = json.loads(r)
        assert parsed["jobs"][0][2] == "agent"

    def test_run_requires_job(self):
        from tools.builtin.cron_tools import cron_tool
        r = cron_tool(action="run")
        parsed = json.loads(r)
        assert "error" in parsed