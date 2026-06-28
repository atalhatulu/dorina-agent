"""Durum makinesi testleri."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestStateMachine:
    def test_create_default(self):
        from orchestrator.state_machine import create_default_machine, AgentState
        sm = create_default_machine()
        assert len(sm.transitions) == len(AgentState)

    def test_state_transitions(self):
        from orchestrator.state_machine import (
            create_default_machine, AgentContext, AgentState
        )
        sm = create_default_machine()
        ctx = AgentContext()
        ctx.state = AgentState.IDLE
        assert ctx.state == AgentState.IDLE

    def test_agent_context(self):
        from orchestrator.state_machine import AgentContext
        ctx = AgentContext()
        ctx.user_input = "test"
        ctx.turn = 1
        assert ctx.user_input == "test"
        assert ctx.turn == 1
        ctx.reset()
        assert ctx.turn == 0
        assert ctx.user_input == ""
