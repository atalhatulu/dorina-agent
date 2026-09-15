"""Deep verification tests for P1 audit findings:
- F07: SubAgent tool permissions, MCP approval, single approval point
- F08: Session encryption, FTS plaintext leak prevention, encrypted summary/title
- F05: Terminal nonzero exit code and stderr retention
- F09: Tool executor timeout enforcement and background task reaping without notifications
- F10: Crew goal assignment, typed subagent error status, crew aggregated status
- F11: Reasoning parser dictionary response safety
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text as _text


# ══════════════════════════════════════════════════════════════════════════
# F07: Tool selection execution permissions & MCP approval
# ══════════════════════════════════════════════════════════════════════════

def test_executor_enforces_allowed_tools_and_toolsets():
    """Executor must reject tools outside allowed_tools or allowed_toolsets."""
    from tools.executor import ToolExecutor
    from tools.registry import ToolDef, ToolRegistry

    reg = ToolRegistry()
    reg.register(ToolDef(name="file_read", description="read", parameters={}, handler=lambda: "content", toolset="file"))
    reg.register(ToolDef(name="term_exec", description="term", parameters={}, handler=lambda: "done", toolset="terminal"))

    ex = ToolExecutor(registry=reg)

    # Allowed tools constraint
    ok_res = ex.execute("file_read", {}, allowed_tools={"file_read"})
    assert ok_res == "content"

    denied_res = ex.execute("term_exec", {}, allowed_tools={"file_read"})
    denied_data = json.loads(denied_res)
    assert denied_data.get("permission_denied") is True
    assert "not permitted" in denied_data.get("error", "")

    # Allowed toolsets constraint
    toolset_denied = ex.execute("term_exec", {}, allowed_toolsets={"file"})
    toolset_data = json.loads(toolset_denied)
    assert toolset_data.get("permission_denied") is True


@pytest.mark.asyncio
async def test_subagent_blocked_tools_cannot_be_called():
    """SubAgent must block recursive delegation, crew, and MCP breakout tools."""
    from tools.delegate import BLOCKED_TOOLS, SubAgent
    from tools.registry import ToolDef, registry

    # Verify BLOCKED_TOOLS contains the right targets
    assert "mcp_call" in BLOCKED_TOOLS
    assert "mcp_list" in BLOCKED_TOOLS
    assert "crew_run" in BLOCKED_TOOLS
    assert "delegate_task" in BLOCKED_TOOLS

    # If SubAgent attempts to call a blocked tool
    agent = SubAgent(goal="test breakout", toolsets=["file", "mcp", "delegation"])
    fake_calls = [
        {"id": "call_1", "function": {"name": "mcp_call", "arguments": "{}"}},
        {"id": "call_2", "function": {"name": "delegate_task", "arguments": "{}"}},
    ]

    with patch.object(agent.engine, "think", new_callable=AsyncMock) as mock_think:
        mock_think.side_effect = [
            {"content": None, "tool_calls": fake_calls},
            {"content": "Final answer after block", "tool_calls": []},
        ]
        result = await agent.run()
        assert result == "Final answer after block"
        assert agent.status == "completed"


@pytest.mark.asyncio
async def test_mcp_call_requires_approval_for_destructive_tool():
    """Calling a destructive MCP tool requires approval and rejects if declined."""
    from security.approval import approval
    from tools.mcp.client import mcp_manager
    from tools.mcp.tool import mcp_call_tool

    # Setup fake server
    mock_client = MagicMock()
    mock_client._connected = True
    fake_tool = MagicMock(name="bash_exec", description="run bash")
    fake_tool.name = "bash_exec"
    mock_client.list_tools = AsyncMock(return_value=[fake_tool])

    with patch.object(mcp_manager, "servers", {"srv1": mock_client}), \
         patch.object(mcp_manager, "list_all_tools", AsyncMock(return_value=[fake_tool])), \
         patch.object(approval, "approve", return_value=False) as mock_approve:

        # Reset cache on tool function
        if hasattr(mcp_call_tool, "_tool_cache"):
            delattr(mcp_call_tool, "_tool_cache")

        res_json = await mcp_call_tool(tool_name="bash_exec", arguments={"cmd": "rm -rf /"})
        res = json.loads(res_json)

        assert res.get("permission_denied") is True
        assert "rejected" in res.get("error", "")
        mock_approve.assert_called_once()
        assert mock_approve.call_args[0][0] == "mcp:bash_exec"


def test_single_approval_point_no_duplicate():
    """Destructive tools should be approved once in executor._setup, not in pipeline hook."""
    from security.approval import approval
    from tools.executor import ToolExecutor
    from tools.registry import ToolDef, ToolRegistry

    reg = ToolRegistry()
    reg.register(ToolDef(
        name="delete_file",
        description="delete",
        parameters={"properties": {"path": {"type": "string"}}, "required": ["path"]},
        handler=lambda path: f"deleted {path}",
        toolset="file",
    ))

    ex = ToolExecutor(registry=reg)
    with patch.object(approval, "approve", return_value=True) as mock_appr:
        res = ex.execute("delete_file", {"path": "/tmp/test.txt"})
        assert res == "deleted /tmp/test.txt"
        assert mock_appr.call_count == 1


# ══════════════════════════════════════════════════════════════════════════
# F08: Session encryption & FTS leak prevention
# ══════════════════════════════════════════════════════════════════════════

def test_session_config_schema_has_encryption():
    """SessionConfig pydantic model must have encryption field."""
    from core.config import SessionConfig
    cfg = SessionConfig(encryption=True)
    assert cfg.encryption is True


def test_encrypted_session_does_not_leak_plaintext_to_fts_or_db(tmp_path, monkeypatch):
    """When encryption is enabled, plaintext messages and summary must NOT exist in raw DB or FTS."""
    import session.manager as sm
    from core.config import settings
    from session.manager import SessionManager, _encrypt, _is_encryption_enabled

    secret_phrase = "TOP_SECRET_USER_TOKEN_998877"
    db_file = tmp_path / "encrypted_sessions.db"
    key_file = tmp_path / ".session_key"

    monkeypatch.setattr(sm, "DB_PATH", db_file)
    monkeypatch.setattr(sm, "_KEY_FILE", key_file)
    monkeypatch.setattr(settings.session, "encryption", True)
    monkeypatch.setattr(sm, "_is_encryption_enabled", lambda: True)

    # Re-bind engine
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    test_engine = create_engine(f"sqlite:///{db_file}")
    sm.Base.metadata.create_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(_text("CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(session_id UNINDEXED, content, tokenize='unicode61')"))
        conn.commit()

    test_session_factory = sessionmaker(bind=test_engine)
    monkeypatch.setattr(sm, "SessionLocal", test_session_factory)

    mgr = SessionManager()
    sid = mgr.create(title="Gizli Oturum")
    mgr.save(
        messages=[{"role": "user", "content": secret_phrase}],
        summary=f"Summary containing {secret_phrase}",
        session_id=sid,
    )

    # 1. Verify load() transparently decrypts
    loaded = mgr.load(sid)
    assert loaded["messages"][0]["content"] == secret_phrase
    assert secret_phrase in loaded["summary"]

    # 2. Inspect raw sqlite file content and FTS table
    with test_engine.connect() as conn:
        # Check session_fts count — must be 0 for encrypted session
        fts_count = conn.execute(_text("SELECT COUNT(*) FROM session_fts WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert fts_count == 0

        # Check raw database rows
        row = conn.execute(_text("SELECT messages, summary, title FROM sessions WHERE id = :sid"), {"sid": sid}).fetchone()
        raw_messages, raw_summary, raw_title = row[0], row[1], row[2]
        assert secret_phrase not in raw_messages
        assert secret_phrase not in raw_summary

    # 3. Verify in-memory encrypted search works without FTS
    search_results = mgr.search(secret_phrase[:10])
    assert len(search_results) >= 1
    assert search_results[0]["id"] == sid

    mgr.current_id = None  # search_content filters out the currently active session
    content_results = mgr.search_content(secret_phrase[:10])
    assert len(content_results) >= 1
    assert content_results[0]["session_id"] == sid


# ══════════════════════════════════════════════════════════════════════════
# F05: Terminal nonzero exit code and stderr retention
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_terminal_retains_nonzero_exit_code():
    """Terminal must return structured error with exit_code for nonzero exits."""
    from tools.builtin.basic import terminal_tool

    res = await terminal_tool("sh -c 'echo fatal error >&2; exit 42'", pty=False, background=False, sandbox=False)
    data = json.loads(res)
    assert data.get("exit_code") == 42
    assert "fatal error" in data.get("stderr", "")


# ══════════════════════════════════════════════════════════════════════════
# F09: Tool executor timeout & background task reaping
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_executor_enforces_timeout():
    """Executor must cancel execution when timeout expires."""
    from tools.executor import ToolExecutor
    from tools.registry import ToolDef, ToolRegistry

    reg = ToolRegistry()

    async def slow_async_handler():
        await asyncio.sleep(0.5)
        return "async done"

    reg.register(ToolDef(name="slow_async", description="slow", parameters={}, handler=slow_async_handler, is_async=True))

    ex = ToolExecutor(registry=reg)
    res = await ex.async_execute("slow_async", {}, timeout=0.05)
    data = json.loads(res)
    assert data.get("timeout") is True
    assert "timed out" in data.get("error", "")


def test_background_task_reaped_without_notification(tmp_path):
    """Background task without notifications must still be reaped and marked done."""
    from tools.builtin.bg_task_tool import task_create_bash
    from bg_tools.task_manager import task_manager

    res_json = task_create_bash("echo 'quick task'", label="test_reap", notify_on_complete=False)
    data = json.loads(res_json)
    task_id = data["task_id"]

    # Wait up to 2 seconds for the background reaper thread to finish
    deadline = time.time() + 2.0
    task = None
    while time.time() < deadline:
        task = task_manager.get(task_id)
        if task and task.status != "running":
            break
        time.sleep(0.05)

    assert task is not None
    assert task.status == "done"
    assert task.finished_at > 0.0
    assert "quick task" in task.result


@pytest.mark.asyncio
async def test_batch_delegation_timeout_cancels_agents():
    """DelegateManager.submit_batch_and_wait must respect timeout and cancel active subagents."""
    from tools.delegate import DelegateManager

    mgr = DelegateManager()

    # Create dummy tasks that would take a long time
    tasks = [{"goal": "task 1"}, {"goal": "task 2"}]

    with patch("tools.delegate.SubAgent.run", new_callable=AsyncMock) as mock_run:
        async def slow_run():
            await asyncio.sleep(1.0)
            return "ok"
        mock_run.side_effect = slow_run

        results = await mgr.submit_batch_and_wait(tasks, timeout=0.05)
        assert len(results) == 2
        for r in results:
            assert r["status"] == "cancelled"
            assert "timed out" in r.get("error", "")


# ══════════════════════════════════════════════════════════════════════════
# F10: Crew goal assignment & typed subagent error status
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_subagent_run_sets_typed_error_status_on_llm_failure():
    """SubAgent.run must not mark status='completed' when LLM errors occur."""
    from tools.delegate import SubAgent

    agent = SubAgent(goal="impossible goal", toolsets=["file"])
    with patch.object(agent.engine, "think", new_callable=AsyncMock) as mock_think:
        mock_think.side_effect = RuntimeError("Provider down")
        res = await agent.run()

        assert agent.status == "error"
        assert "Provider down" in agent.error
        data = json.loads(res)
        assert "LLM error" in data.get("error", "")


@pytest.mark.asyncio
async def test_crew_assigns_focused_goal_and_reports_real_status():
    """AgentCrew must preserve member focus and aggregate failed status when all members fail."""
    from agents.crew import AgentCrew

    crew_inst = AgentCrew()
    crew_inst.add_member("planner", "Create initial milestones")
    crew_inst.add_member("reviewer", "Audit security risks")

    assert crew_inst.member_count() == 2
    # Verify _role_goal contains the focus
    goal_planner = crew_inst._role_goal(crew_inst.members[0], "Build app")
    assert "Milestones" in goal_planner or "milestones" in goal_planner
    assert "planner" in goal_planner

    # Simulate run where members fail
    with patch.object(AgentCrew, "run_member", new_callable=AsyncMock) as mock_run_member:
        mock_run_member.side_effect = [
            {"role": "planner", "status": "failed", "error": "err1", "result": ""},
            {"role": "reviewer", "status": "failed", "error": "err2", "result": ""},
        ]
        summary_json = await crew_inst.run_crew("Build app")
        summary = json.loads(summary_json)
        assert summary["status"] == "failed"


# ══════════════════════════════════════════════════════════════════════════
# F11: Reasoning parser dictionary response safety
# ══════════════════════════════════════════════════════════════════════════

def test_reasoning_parse_response_handles_dict_safely():
    """ReasoningEngine._parse_response must accept already-parsed dict responses without error."""
    from orchestrator.reasoning import ReasoningEngine

    engine = ReasoningEngine()
    fake_dict_resp = {
        "content": "Hello world",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    parsed = engine._parse_response(fake_dict_resp)
    assert parsed["content"] == "Hello world"
