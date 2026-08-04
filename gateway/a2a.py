"""A2A Server (Agent2Agent) Endpoint"""
from fastapi import APIRouter, HTTPException, Request, Depends
import uuid

from gateway.auth import verify_token, is_auth_enabled
from orchestrator.experimental_loop import loop_v2
from session.manager import manager as session_manager

a2a_router = APIRouter()

async def _a2a_auth(request: Request):
    if not is_auth_enabled():
        return
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.headers.get("X-Dashboard-Token", "")
    if not verify_token(token):
        raise HTTPException(401, "Unauthorized")

@a2a_router.get("/.well-known/agent.json")
async def get_agent_card():
    return {
        "name": "Dorina",
        "description": "CLI AI agent endpoint",
        "url": "http://127.0.0.1:5792/a2a",
        "provider": {"organization": "atalhatulu"},
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": [{"id": "dorina-chat", "name": "General chat & code", "description": "Run Dorina"}]
    }

def _jsonrpc_err(req_id, code: int, message: str):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,
            "message": message
        }
    }

@a2a_router.post("/a2a", dependencies=[Depends(_a2a_auth)])
async def handle_a2a_rpc(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return _jsonrpc_err(None, -32700, "Parse error")
        
    if not isinstance(payload, dict):
        return _jsonrpc_err(None, -32700, "Parse error")
        
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})
    
    if method == "tasks/send":
        try:
            message = params.get("message", {})
            parts = message.get("parts", [])
            text = parts[0].get("text", "") if parts else ""
            if not text:
                return _jsonrpc_err(req_id, -32602, "Invalid params")
                
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            
            # Run loop_v2
            reply = await loop_v2.process(text)
            
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "id": task_id,
                    "status": "completed",
                    "sessionId": session_manager.current_id or "",
                    "artifacts": [
                        {
                            "name": "response",
                            "parts": [{"text": reply}]
                        }
                    ]
                }
            }
        except Exception as e:
            return _jsonrpc_err(req_id, -32603, f"Internal error: {str(e)}")
            
    elif method == "tasks/get":
        task_id = params.get("id")
        if not task_id:
             return _jsonrpc_err(req_id, -32602, "Invalid params")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": task_id,
                "status": "completed"
            }
        }
        
    else:
        return _jsonrpc_err(req_id, -32601, "Method not implemented")
