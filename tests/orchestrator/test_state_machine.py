"""Tests for orchestrator/state_machine.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAgentState:
    def test_state_values(self):
        from orchestrator.state_machine import AgentState
        assert AgentState.IDLE.value == "idle"
        assert AgentState.THINKING.value == "thinking"
        assert AgentState.TOOL_CALLING.value == "tool"
        assert AgentState.DONE.value == "done"
        assert AgentState.ERROR.value == "error"

    def test_all_states_unique(self):
        from orchestrator.state_machine import AgentState
        values = [s.value for s in AgentState]
        assert len(values) == len(set(values))


class TestAgentContext:
    def test_initial_state(self):
        from orchestrator.state_machine import AgentContext
        ctx = AgentContext()
        assert ctx.state.value == "idle"
        assert ctx.turn == 0
        assert ctx.user_input == ""
        assert ctx.error is None

    def test_reset(self):
        from orchestrator.state_machine import AgentContext
        ctx = AgentContext()
        ctx.user_input = "test"
        ctx.turn = 5
        ctx.tool_calls = [{"name": "test"}]
        ctx.reset()
        assert ctx.turn == 0
        assert ctx.user_input == ""
        assert ctx.tool_calls == []

    def test_metadata(self):
        from orchestrator.state_machine import AgentContext
        ctx = AgentContext()
        ctx.metadata.update({"key": "value"})
        assert ctx.metadata.get("key") == "value"


class TestStateMachine:
    def test_create_default(self):
        from orchestrator.state_machine import create_default_machine, AgentState
        sm = create_default_machine()
        assert len(sm.transitions) == len(AgentState)
        assert sm.history == []

    def test_add_transition(self):
        from orchestrator.state_machine import StateMachine, AgentState
        sm = StateMachine()
        sm.add_transition(AgentState.IDLE, AgentState.THINKING, "start")
        assert len(sm.transitions[AgentState.IDLE]) == 1
        assert sm.transitions[AgentState.IDLE][0].to_state == AgentState.THINKING

    def test_transition_conditions(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()
        ctx.state = AgentState.IDLE

        sm.add_transition(AgentState.IDLE, AgentState.THINKING, "start")
        next_state, condition = sm._get_next_state(ctx)
        assert next_state == AgentState.THINKING
        assert condition == "start"

    def test_has_tools_condition(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()
        ctx.state = AgentState.THINKING
        ctx.metadata.update({"has_tools": True})
        sm.add_transition(AgentState.THINKING, AgentState.TOOL_CALLING, "has_tools")
        next_state, condition = sm._get_next_state(ctx)
        assert next_state == AgentState.TOOL_CALLING

    def test_planning_only_condition(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()
        ctx.state = AgentState.THINKING
        ctx.metadata.update({"planning_retry": True})
        sm.add_transition(AgentState.THINKING, AgentState.THINKING, "planning_only")
        next_state, condition = sm._get_next_state(ctx)
        assert next_state == AgentState.THINKING

    def test_default_transition_idle(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()
        ctx.state = AgentState.IDLE
        next_state, condition = sm._get_next_state(ctx)
        assert next_state == AgentState.THINKING

    def test_default_transition_error(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()
        ctx.state = AgentState.ERROR
        next_state, condition = sm._get_next_state(ctx)
        assert next_state == AgentState.FALLBACK

    def test_run(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()

        async def idle_handler(c):
            c.final_response = "done"
            # Force done
            c.state = AgentState.DONE

        sm.add_transition(AgentState.IDLE, AgentState.DONE, "done")

        import asyncio
        result = asyncio.run(sm.run(ctx, {
            "idle": idle_handler,
        }))
        assert result == "done"

    def test_run_error(self):
        from orchestrator.state_machine import StateMachine, AgentContext, AgentState
        sm = StateMachine()
        ctx = AgentContext()

        async def bad_handler(c):
            raise RuntimeError("something went wrong")

        sm.add_transition(AgentState.IDLE, AgentState.ERROR, "error")
        sm.add_transition(AgentState.ERROR, AgentState.DONE, "done")

        import asyncio
        result = asyncio.run(sm.run(ctx, {
            "idle": bad_handler,
        }))
        assert "Hata" in result

    def test_reset_history(self):
        from orchestrator.state_machine import StateMachine, AgentContext
        sm = StateMachine()
        ctx = AgentContext()
        ctx.user_input = "test"
        sm.reset_history(ctx)
        assert ctx.user_input == ""
