"""Deep verification tests for P0 audit findings (F01, F02, F03, F04, F06)."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.config import DashboardConfig, Settings
from gateway.app import app, _loop_lock
from gateway.auth import (
    is_auth_enabled,
    is_origin_allowed,
    reload_token,
    reset_token_cache,
    verify_token,
)
from session.manager import SessionManager, SessionModel


@pytest.fixture(autouse=True)
def clean_auth_state(monkeypatch):
    """Ensure clean auth token and cache for every test."""
    monkeypatch.delenv("DORINA_DASHBOARD_TOKEN", raising=False)
    reset_token_cache()
    yield
    reset_token_cache()


@pytest.fixture
def isolated_manager(monkeypatch):
    """Isolated in-memory session manager."""
    import session.manager as sm_mod

    engine = create_engine("sqlite:///:memory:")
    sm_mod.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE VIRTUAL TABLE session_fts USING fts5(session_id UNINDEXED, content)")
        )
    monkeypatch.setattr(sm_mod, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(sm_mod, "_encrypt", lambda value: value)
    monkeypatch.setattr(sm_mod, "_decrypt", lambda value: value)
    monkeypatch.setattr(sm_mod, "count_messages_tokens", lambda msgs: len(msgs))
    mgr = sm_mod.SessionManager()
    yield mgr
    mgr.db.close()
    engine.dispose()


# ── F06: Dashboard Config, Token Precedence, and Origin Policy ──

class TestF06DashboardConfigAndAuth:
    def test_dashboard_config_schema(self):
        cfg = DashboardConfig(token="secret-123", allowed_origins=["http://custom.origin:5792"])
        assert cfg.token == "secret-123"
        assert "http://custom.origin:5792" in cfg.allowed_origins

        s = Settings(dashboard={"token": "yaml-tok-456", "port": 5792})
        assert s.dashboard.token == "yaml-tok-456"
        assert s.dashboard.port == 5792

    def test_token_source_precedence(self, monkeypatch):
        # 1. Neither config nor env -> None / False
        monkeypatch.setattr("core.config.settings.dashboard.token", "")
        reset_token_cache()
        assert not is_auth_enabled()
        assert verify_token("any-token") is True  # auth disabled -> passes

        # 2. Env var fallback
        monkeypatch.setenv("DORINA_DASHBOARD_TOKEN", "env-secret-token")
        reset_token_cache()
        assert is_auth_enabled()
        assert verify_token("env-secret-token") is True
        assert verify_token("wrong-token") is False

        # 3. Config overrides env var
        monkeypatch.setattr("core.config.settings.dashboard.token", "config-secret-token")
        reset_token_cache()
        assert is_auth_enabled()
        assert verify_token("config-secret-token") is True
        assert verify_token("env-secret-token") is False

    def test_origin_allowed_policy(self, monkeypatch):
        # Non-browser clients (no Origin) are allowed
        assert is_origin_allowed(None) is True
        assert is_origin_allowed("") is True

        # Default localhost origins
        assert is_origin_allowed("http://localhost:5792") is True
        assert is_origin_allowed("http://127.0.0.1:5792") is True
        assert is_origin_allowed("http://localhost:5792/") is True

        # Host matching fallback
        assert is_origin_allowed("http://my-host.local:5792", host="my-host.local:5792") is True

        # Foreign / untrusted origin
        assert is_origin_allowed("http://malicious-website.com") is False
        assert is_origin_allowed("http://attacker.com:5792") is False

        # Configured custom allowed_origins
        monkeypatch.setattr(
            "core.config.settings.dashboard.allowed_origins",
            ["http://trusted-internal.corp:5792"],
        )
        assert is_origin_allowed("http://trusted-internal.corp:5792") is True
        assert is_origin_allowed("http://malicious-website.com") is False

    def test_rest_auth_enforcement(self, monkeypatch):
        monkeypatch.setattr("core.config.settings.dashboard.token", "rest-p0-token")
        reset_token_cache()

        client = TestClient(app)

        # Unauthenticated -> 401
        res = client.get("/api/status")
        assert res.status_code == 401
        assert "Unauthorized" in res.json().get("detail", "")

        # Invalid token header -> 401
        res = client.get("/api/status", headers={"X-Dashboard-Token": "bad-token"})
        assert res.status_code == 401

        # Valid token via header -> 200
        res = client.get("/api/status", headers={"X-Dashboard-Token": "rest-p0-token"})
        assert res.status_code == 200

        # Valid token via query param -> 200
        res = client.get("/api/status?token=rest-p0-token")
        assert res.status_code == 200

    def test_websocket_origin_and_auth_rejection(self, monkeypatch):
        monkeypatch.setattr("core.config.settings.dashboard.token", "ws-p0-token")
        reset_token_cache()

        client = TestClient(app)

        # 1. Foreign origin is rejected (4403)
        with client.websocket_connect(
            "/ws/chat?token=ws-p0-token",
            headers={"Origin": "http://evil-attacker.com"},
        ) as ws:
            msg = ws.receive_json()
            assert msg.get("type") == "error"
            assert "Forbidden origin" in msg.get("content", "")

        with client.websocket_connect(
            "/ws/events?token=ws-p0-token",
            headers={"Origin": "http://evil-attacker.com"},
        ) as ws:
            msg = ws.receive_json()
            assert msg.get("type") == "error"
            assert "Forbidden origin" in msg.get("content", "")

        # 2. Trusted origin, but invalid token is rejected (4401)
        with client.websocket_connect(
            "/ws/chat?token=wrong-token",
            headers={"Origin": "http://localhost:5792"},
        ) as ws:
            msg = ws.receive_json()
            assert msg.get("type") == "error"
            assert "Unauthorized" in msg.get("content", "")

        # 3. Trusted origin + valid token in header succeeds
        with client.websocket_connect(
            "/ws/events",
            headers={
                "Origin": "http://localhost:5792",
                "X-Dashboard-Token": "ws-p0-token",
            },
        ) as ws:
            # First message sent upon connect is the initial workspace snapshot
            snap = ws.receive_json()
            assert snap.get("type") == "snapshot"

            # Ping-pong keepalive test
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data.get("type") == "pong"


# ── F03: Session Isolation and Mutable Global State ──

class TestF03SessionIsolation:
    def test_load_is_read_only_by_default(self, isolated_manager):
        sid_a = isolated_manager.create(title="Session A")
        sid_b = isolated_manager.create(title="Session B")
        assert isolated_manager.current_id == sid_b

        # Loading session A must NOT mutate current_id to sid_a
        loaded = isolated_manager.load(sid_a)
        assert loaded is not None
        assert loaded["id"] == sid_a
        assert isolated_manager.current_id == sid_b

        # Explicit activate switches current_id
        assert isolated_manager.activate(sid_a) is True
        assert isolated_manager.current_id == sid_a

    def test_save_to_explicit_session_id(self, isolated_manager):
        sid_a = isolated_manager.create(title="Session A")
        sid_b = isolated_manager.create(title="Session B")
        assert isolated_manager.current_id == sid_b

        msgs_a = [{"role": "user", "content": "for session A"}]
        # Save explicitly to sid_a while current_id is sid_b
        isolated_manager.save(msgs_a, session_id=sid_a)

        assert isolated_manager.current_id == sid_b
        assert isolated_manager.load(sid_a)["messages"] == msgs_a
        assert isolated_manager.load(sid_b)["messages"] == []

    def test_api_get_session_does_not_mutate_active_session(self, monkeypatch):
        from gateway.app import session_manager

        sid_1 = session_manager.create(title="Active Current")
        sid_2 = session_manager.create(title="Old History")
        session_manager.current_id = sid_1

        client = TestClient(app)
        res = client.get(f"/api/sessions/{sid_2}")
        assert res.status_code == 200
        assert res.json()["id"] == sid_2

        # Active session must still be sid_1
        assert session_manager.current_id == sid_1

    @pytest.mark.asyncio
    async def test_experimental_loop_snapshots_messages_during_save(self, monkeypatch):
        from orchestrator.experimental_loop import AgentLoopV2
        from core.config import settings

        monkeypatch.setattr(settings.session, "auto_save", True)

        loop = AgentLoopV2()
        loop.context.messages = [
            {"role": "user", "content": f"msg {i}"} for i in range(6)
        ]

        saved_payloads = []

        def mock_save(messages, **kwargs):
            # Record a copy of what was received
            saved_payloads.append(list(messages))

        monkeypatch.setattr("orchestrator.experimental_loop.session_manager.save", mock_save)

        # Trigger schedule save
        loop._schedule_save(quick=True)

        # Concurrently mutate the loop's context messages immediately
        loop.context.messages.append({"role": "user", "content": "mutation after schedule"})

        # Allow event loop background task to run
        await asyncio.sleep(0.05)

        assert len(saved_payloads) == 1
        # Saved messages must have 6 items (the snapshot), not the mutated 7
        assert len(saved_payloads[0]) == 6
        assert saved_payloads[0][-1]["content"] == "msg 5"

    @pytest.mark.asyncio
    async def test_loop_lock_guarantees_mutual_exclusion(self):
        """Verify _loop_lock serializes concurrent executions."""
        execution_order = []

        async def worker(worker_id: int):
            async with _loop_lock:
                execution_order.append(f"start_{worker_id}")
                await asyncio.sleep(0.05)
                execution_order.append(f"end_{worker_id}")

        await asyncio.gather(worker(1), worker(2))

        # Must not interleave: start_1 -> end_1 -> start_2 -> end_2
        assert execution_order in (
            ["start_1", "end_1", "start_2", "end_2"],
            ["start_2", "end_2", "start_1", "end_1"],
        )


# ── F01, F04, F02: End-to-End Verifications ──

class TestF01F04F02Verifications:
    @pytest.mark.asyncio
    async def test_f04_terminal_sandbox_fail_closed(self, monkeypatch):
        from tools.builtin import terminal

        # Simulate sandbox returning None
        monkeypatch.setattr(terminal, "_run_in_sandbox", lambda cmd, timeout: None)

        # Attempting execution with sandbox=True MUST fail closed and not touch host
        with patch("subprocess.run") as mock_host_subproc, patch("subprocess.Popen") as mock_host_popen:
            result = json.loads(await terminal.terminal_tool("echo safe", sandbox=True))
            assert "error" in result
            assert "refused" in result["error"].lower() or "sandbox" in result["error"].lower()
            mock_host_subproc.assert_not_called()
            mock_host_popen.assert_not_called()

    @pytest.mark.asyncio
    async def test_f02_loop_terminates_on_repeated_errors(self, monkeypatch):
        from orchestrator.experimental_loop import AgentLoopV2
        from orchestrator import experimental_loop as module

        loop = AgentLoopV2()
        loop._session_titled = True
        loop._skills_injected = True

        mock_reasoning = AsyncMock()
        mock_reasoning.think = AsyncMock(
            return_value={
                "tool_calls": [{"id": "c1", "name": "unknown_tool", "arguments": {}}],
                "content": "",
            }
        )
        loop.reasoning = mock_reasoning

        with patch.object(module, "_MAX_LOOP_ITERATIONS", 3), patch.object(module.modes, "is_on", return_value=False):
            reply = await loop.process("test repeating errors")

        # The loop must gracefully terminate and report exhaustion/limit reached
        assert loop._loop_iterations <= 3
        assert isinstance(reply, str)
