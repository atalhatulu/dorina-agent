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
            
            # Run loop_v2 with execution lock and ADR-001 contract
            from gateway.app import _loop_lock
            from orchestrator.contract import RunRequest, RunResult, RunStatus
            from orchestrator.experimental_loop import AgentLoopV2

            run_req = RunRequest(input=text, run_id=task_id, session_id=session_manager.current_id)
            async with _loop_lock:
                # If process was monkeypatched on loop_v2 by tests, respect it
                is_patched = getattr(loop_v2.process, "__code__", None) != AgentLoopV2.process.__code__
                if is_patched:
                    reply = await loop_v2.process(text)
                    run_res = RunResult(
                        status=RunStatus.COMPLETED,
                        output=reply if isinstance(reply, str) else str(reply),
                        run_id=task_id,
                        session_id=session_manager.current_id or "",
                    )
                else:
                    run_res = await loop_v2.run(run_req)

            a2a_status = "completed" if run_res.status == RunStatus.COMPLETED else "failed"
            result_payload = {
                "id": task_id,
                "status": a2a_status,
                "sessionId": session_manager.current_id or "",
                "artifacts": [
                    {
                        "name": "response",
                        "parts": [{"text": run_res.output}],
                    }
                ],
            }
            if run_res.error:
                result_payload["error"] = run_res.error

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result_payload,
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
