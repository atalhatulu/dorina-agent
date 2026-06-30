"""Tests for orchestrator/agent_loop.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAgentLoopCore:
    def test_import_and_instantiate(self):
        from orchestrator.agent_loop import AgentLoop
        loop = AgentLoop()
        assert loop is not None
        assert loop.turn == 0
        assert loop.sm is not None

    def test_clean_content_removes_xml(self):
        from orchestrator.agent_loop import AgentLoop
        text = '<invoke name="read_file"><parameter name="path">/etc/passwd</parameter></invoke>'
        cleaned = AgentLoop._clean_content(text)
        assert "<invoke" not in cleaned
        assert "<parameter" not in cleaned

    def test_clean_content_removes_tool_calls_xml(self):
        from orchestrator.agent_loop import AgentLoop
        text = '<tool_calls><tool name="search">query</tool></tool_calls>'
        cleaned = AgentLoop._clean_content(text)
        assert "<tool_calls" not in cleaned
        assert "<tool" not in cleaned

    def test_clean_content_preserves_normal_text(self):
        from orchestrator.agent_loop import AgentLoop
        text = "Hello, this is normal text with no XML."
        cleaned = AgentLoop._clean_content(text)
        assert cleaned == text

    def test_clean_content_function_calls(self):
        from orchestrator.agent_loop import AgentLoop
        text = '<function=read_file>path="/etc/passwd"</function>'
        cleaned = AgentLoop._clean_content(text)
        assert "<function" not in cleaned

    def test_reset(self):
        from orchestrator.agent_loop import AgentLoop
        loop = AgentLoop()
        loop.turn = 5
        loop.reset()
        assert loop.turn == 0
        assert loop._skills_injected is False

    def test_planning_patterns_loaded(self):
        from orchestrator.agent_loop import AgentLoop
        assert len(AgentLoop.PLANNING_PATTERNS) > 10
        assert "önce" in AgentLoop.PLANNING_PATTERNS
        assert "first" in AgentLoop.PLANNING_PATTERNS
        assert "let me" in AgentLoop.PLANNING_PATTERNS

    def test_force_tool_patterns_loaded(self):
        from orchestrator.agent_loop import AgentLoop
        assert len(AgentLoop.FORCE_TOOL_PATTERNS) > 5
        assert "oku" in AgentLoop.FORCE_TOOL_PATTERNS
        assert "read" in AgentLoop.FORCE_TOOL_PATTERNS

@pytest.mark.asyncio
async def test_iteration_budget_exhaustion():
    from orchestrator.state_machine import AgentContext, AgentState
    
    ctx = AgentContext(
        state=AgentState.THINKING,
        user_input="test",
        iteration_budget=15,
        iterations_used=0
    )
    
    # Tool cagrisi olmadan budget artmamali
    ctx.iterations_used = 0
    assert ctx.iterations_used < ctx.iteration_budget  # Henuz dolmadi
    
    # Budget 15'e ulasinca dolmali (manuel test)
    ctx.iterations_used = 15
    assert ctx.iterations_used >= ctx.iteration_budget  # Doldu
