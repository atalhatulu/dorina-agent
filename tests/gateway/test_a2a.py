"""Tests for A2A Server endpoints."""

import pytest
from fastapi.testclient import TestClient
from gateway.app import app
import gateway.a2a

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    """Disable auth for most tests."""
    monkeypatch.setattr(gateway.a2a, "is_auth_enabled", lambda: False)

def test_agent_card():
    """1. GET /.well-known/agent.json"""
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Dorina"
    assert "capabilities" in data

def test_tasks_send(monkeypatch):
    """2. POST /a2a tasks/send"""
    async def mock_process(text: str, *args, **kwargs):
        return f"mock reply to {text}"
        
    monkeypatch.setattr(gateway.a2a.loop_v2, "process", mock_process)
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "message": {
                "parts": [{"text": "hello a2a"}]
            }
        }
    }
    res = client.post("/a2a", json=payload)
    assert res.status_code == 200
    data = res.json()
    
    assert data["id"] == 1
    assert data["result"]["status"] == "completed"
    assert "task_" in data["result"]["id"]
    artifacts = data["result"]["artifacts"]
    assert artifacts[0]["parts"][0]["text"] == "mock reply to hello a2a"

def test_tasks_get():
    """3. POST /a2a tasks/get"""
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tasks/get",
        "params": {"id": "task_123"}
    }
    res = client.post("/a2a", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["result"]["status"] == "completed"
    
    # Missing ID
    bad_payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tasks/get",
        "params": {}
    }
    res = client.post("/a2a", json=bad_payload)
    assert res.json()["error"]["code"] == -32602

def test_unknown_method():
    """4. Unknown method -> -32601"""
    payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "unknown/method",
        "params": {}
    }
    res = client.post("/a2a", json=payload)
    assert res.json()["error"]["code"] == -32601

def test_invalid_json():
    """5. Invalid JSON -> -32700"""
    res = client.post("/a2a", data="invalid { json")
    assert res.status_code == 200
    assert res.json()["error"]["code"] == -32700

def test_auth_enabled_no_token(monkeypatch):
    """6. Auth açıkken token yoksa -> 401"""
    monkeypatch.setattr(gateway.a2a, "is_auth_enabled", lambda: True)
    # Gerçek verify_token, auth kapalıyken (token yapılandırılmamışsa) boş token'a
    # True döner — bu yüzden test verify_token'ı da mock'lamalı (kod değil, test kusuru).
    monkeypatch.setattr(gateway.a2a, "verify_token", lambda t: t == "secret")

    res = client.post("/a2a", json={"jsonrpc": "2.0", "method": "tasks/get", "params": {"id": "1"}})
    assert res.status_code == 401

    # Valid token (mocked verify_token)
    res2 = client.post("/a2a", json={"jsonrpc": "2.0", "method": "tasks/get", "params": {"id": "1"}}, headers={"Authorization": "Bearer secret"})
    assert res2.status_code == 200
