"""Regression coverage for CLI, sandbox routing, terminal and crew wiring."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("current_id", [None, "existing-session"])
async def test_cli_startup(current_id):
    import app

    manager = SimpleNamespace(current_id=current_id, create=Mock(return_value="new-session"))
    with patch.object(app, "session_manager", manager), patch.object(app, "print_startup_banner") as banner:
        cli = app.DorinaApp()
        await cli.startup()
    assert cli.session_id == (current_id or "new-session")
    banner.assert_called_once_with(session_id=cli.session_id)
    assert manager.create.call_count == (0 if current_id else 1)


@pytest.mark.asyncio
async def test_cli_single_query_uses_process():
    import app

    with patch.object(app.loop, "process", new_callable=AsyncMock, return_value="answer") as process, patch.object(app, "print_info") as display:
        await app.DorinaApp().run_single_query("question")
    process.assert_awaited_once_with("question")
    display.assert_called_once_with("answer")


@pytest.mark.asyncio
async def test_cli_interactive_uses_process():
    import app

    cli = app.DorinaApp()

    async def prompt(_):
        cli.running = False
        return "question"

    cli._prompt_session = SimpleNamespace(prompt_async=prompt)
    with patch("ui.repl.get_prompt", return_value="> "), patch.object(app.loop, "process", new_callable=AsyncMock, return_value="answer") as process, patch.object(app, "print_info"):
        await cli.run_interactive()
    process.assert_awaited_once_with("question")


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, None])
@pytest.mark.parametrize("tool_name,helper", [
    ("terminal_tool", "_run_in_sandbox"),
    ("batch_python_tool", "_run_python_in_sandbox"),
])
async def test_unavailable_sandbox_never_runs_on_host(sandbox, tool_name, helper):
    from tools.builtin import terminal

    with patch.object(terminal, "_sandbox_enabled_in_config", return_value=True), patch.object(terminal, helper, return_value=None), patch("subprocess.run") as run, patch("subprocess.Popen") as popen:
        result = await getattr(terminal, tool_name)("print('hello')", sandbox=sandbox)
    assert "host execution refused" in json.loads(result)["error"]
    run.assert_not_called()
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_terminal_applies_cwd(tmp_path):
    from tools.builtin.terminal import terminal_tool

    result = await terminal_tool("pwd", cwd=str(tmp_path), sandbox=False)
    assert result.strip() == str(tmp_path)


@pytest.mark.asyncio
async def test_terminal_reports_exit_status():
    from tools.builtin.terminal import terminal_tool

    result = json.loads(await terminal_tool("echo output; echo failure >&2; exit 7", sandbox=False))
    assert result["exit_code"] == 7
    assert "error" in result
    assert result["stdout"].strip() == "output"
    assert result["stderr"].strip() == "failure"


@pytest.mark.parametrize("parallel", [True, False])
@pytest.mark.parametrize("roles", [None, ["researcher", "reviewer"]])
def test_crew_tool_creates_members(parallel, roles):
    from tools.builtin.crew_tools import crew_run_tool

    with patch("agents.crew.SubAgent") as agent:
        agent.return_value.run = AsyncMock(return_value="result")
        agent.return_value.status = "completed"
        agent.return_value.turn_count = 1
        agent.return_value.error = ""
        result = json.loads(crew_run_tool("shared task", roles=roles, parallel=parallel))
    assert result["status"] == "completed"
    assert len(result["members"]) == (len(roles) if roles else 4)
    assert agent.call_count == len(result["members"])
    assert all("shared task" in call.kwargs["goal"] for call in agent.call_args_list)


@pytest.mark.parametrize("focus", ["check security", ""])
def test_crew_goal_preserves_focus(focus):
    from agents.crew import AgentCrew

    goal = AgentCrew()._role_goal({"role": "reviewer", "goal": focus}, "shared task")
    assert "shared task" in goal
    assert ("Focus:" in goal) == bool(focus)
    if focus:
        assert focus in goal
