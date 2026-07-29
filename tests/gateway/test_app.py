"""Tests for gateway/app.py"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from gateway.app import app
    return TestClient(app)


class TestAPI:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_status_endpoint(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert "name" in data
        assert data["name"] == "dorina-agent"
        assert "version" in data
        assert "sessions" in data

    def test_list_sessions(self, client):
        r = client.get("/api/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_list_sessions_with_limit(self, client):
        r = client.get("/api/sessions?limit=3")
        assert r.status_code == 200
        data = r.json()
        assert len(data["sessions"]) <= 3

    def test_create_session(self, client):
        r = client.post("/api/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data
        assert data["title"] == "Web Session"

    def test_get_nonexistent_session_returns_404(self, client):
        r = client.get("/api/sessions/nonexistent_12345")
        assert r.status_code == 404

    def test_delete_nonexistent_session_returns_404(self, client):
        r = client.delete("/api/sessions/nonexistent_12345")
        assert r.status_code == 404


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_connect(self, client):
        """WebSocket endpoint should accept connection."""
        pytest.importorskip("asgi_lifespan")
        from asgi_lifespan import LifespanManager
        from gateway.app import app

        async with LifespanManager(app):
            async with client.websocket_connect("/ws/chat") as ws:
                data = ws.receive_json()
                assert data["type"] == "session"
                assert "session_id" in data
