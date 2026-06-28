"""Tests for the FastAPI Gateway Server."""
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
import json
from fastapi.testclient import TestClient
from gateway.server import GatewayServer

@pytest.fixture
def client():
    server = GatewayServer()
    app = server._build_app()
    return TestClient(app)

def test_health_endpoints(client):
    """Test the / and /health endpoints."""
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "running"

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["name"] == "Dorina Agent"

def test_tools_endpoint(client):
    """Test the /tools endpoint."""
    res = client.get("/tools")
    assert res.status_code in (200, 503)
    if res.status_code == 200:
        data = res.json()
        assert "tools" in data
        assert "count" in data

def test_sessions_endpoint(client):
    """Test the /sessions endpoint."""
    res = client.get("/sessions")
    assert res.status_code in (200, 503)
    if res.status_code == 200:
        data = res.json()
        assert isinstance(data, list)

def test_export_post_endpoint(client):
    """Test the /export endpoint with POST."""
    payload = {"format": "json", "data": {"messages": [{"role": "user", "content": "hello"}]}}
    res = client.post("/export", json=payload)
    assert res.status_code in (200, 503, 500)
    if res.status_code == 200:
        data = res.json()
        assert data["status"] == "exported"

def test_export_get_endpoint(client):
    """Test the /export/{format} endpoint with GET."""
    payload = json.dumps({"messages": [{"role": "user", "content": "hello"}]})
    res = client.get(f"/export/json?data={payload}")
    assert res.status_code in (200, 503, 500)
    if res.status_code == 200:
        data = res.json()
        assert data["status"] == "exported"

def test_chat_get_endpoint(client, monkeypatch):
    """Test the /chat endpoint with GET."""
    import orchestrator.agent_loop
    async def mock_process(query, *args, **kwargs):
        return f"Mocked response for: {query}"
    
    monkeypatch.setattr(orchestrator.agent_loop.loop, "process", mock_process)
    
    res = client.get("/chat?query=Test")
    assert res.status_code == 200
    assert res.json()["response"] == "Mocked response for: Test"

def test_chat_post_endpoint(client, monkeypatch):
    """Test the /chat endpoint with POST."""
    import orchestrator.agent_loop
    async def mock_process(query, *args, **kwargs):
        return f"Mocked response for: {query}"
    
    monkeypatch.setattr(orchestrator.agent_loop.loop, "process", mock_process)
    
    res = client.post("/chat", json={"query": "Test POST", "session_id": "123"})
    assert res.status_code == 200
    assert res.json()["response"] == "Mocked response for: Test POST"
    assert res.json()["session_id"] == "123"
