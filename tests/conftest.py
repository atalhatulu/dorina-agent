"""Shared fixtures and mocks for all tests."""
import sys
import json
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def fresh_event_bus():
    """Fresh EventBus instance per test."""
    from core.event_bus import EventBus
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def fresh_registry():
    """Fresh ToolRegistry instance per test."""
    from tools.registry import ToolRegistry
    reg = ToolRegistry()
    yield reg


@pytest.fixture
def patch_registry(fresh_registry):
    """Patch the global registry with a fresh one for executor tests."""
    import tools.registry as treg
    import tools.executor as texec
    orig = treg.registry
    treg.registry = fresh_registry
    texec.registry = fresh_registry  # executor has its own import binding
    yield fresh_registry
    treg.registry = orig
    texec.registry = orig


@pytest.fixture
def sample_handler():
    """Simple sync handler for tool tests."""
    def handler(a: int = 0, b: int = 0) -> str:
        return json.dumps({"result": a + b})
    return handler


@pytest.fixture
def mock_config(tmp_path):
    """Mock config file for Settings.load()."""
    from core.config import Settings
    import os
    old_env = dict(os.environ)
    os.environ["DORINA_TEST"] = "1"
    yield Settings.load()
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture
def fresh_auth():
    """Fresh Auth instance per test."""
    from security.auth import Auth
    return Auth()


@pytest.fixture
def fresh_approval():
    """Fresh Approval instance per test."""
    from security.approval import Approval
    appr = Approval(mode="off")
    yield appr


@pytest.fixture
def fresh_context():
    """Fresh Context instance per test."""
    from orchestrator.context import Context
    return Context()


@pytest.fixture
def fresh_agent_context():
    """Fresh AgentContext instance per test."""
    from orchestrator.state_machine import AgentContext
    return AgentContext()


@pytest.fixture
def fresh_sm():
    """Default state machine."""
    from orchestrator.state_machine import create_default_machine
    return create_default_machine()


@pytest.fixture
def fresh_metrics():
    """Fresh Metrics instance per test."""
    from monitoring.metrics import Metrics
    return Metrics()


@pytest.fixture
def mock_metrics_hook():
    """Patches monitoring hooks to avoid side effects."""
    import monitoring.metrics as mm
    original = mm.metrics
    from monitoring.metrics import Metrics
    mm.metrics = Metrics()
    yield mm.metrics
    mm.metrics = original
