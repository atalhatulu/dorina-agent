"""
Gelişmiş tool'lar — Deep Research, MCP, Delegate, Email, Audio.
"""

from __future__ import annotations
import json
import asyncio

from tools.registry import register_tool, registry
from core.logger import log


# ─── DELEGATE TASK (Alt-Agent) ───────────────────────────

@register_tool(
    name="delegate_task",
    description="Bir alt-agent'a görev ver. Paralel çalışır, sonucu özet olarak döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "Alt-agent'ın yapacağı görev",
            },
            "context": {
                "type": "string",
                "description": "Alt-agent'a verilecek bağlam/bilgi",
                "default": "",
            },
        },
        "required": ["goal"],
    },
    toolset="delegation",
)
async def delegate_task_tool(goal: str, context: str = "") -> str:
    """Alt-agent'a görev ver, sonucu bekle."""
    from tools.delegate import delegate
    
    agent_id = delegate.submit(goal=goal, context=context)
    result = await delegate.get_result(agent_id, timeout=120)
    
    agent = delegate.active.get(agent_id)
    return json.dumps({
        "agent_id": agent_id,
        "result": result,
        "status": agent.status if agent else "unknown",
        "turns": agent.turn_count if agent else 0,
    }, ensure_ascii=False)


# ─── DELEGATE BATCH (Paralel Alt-Agent) ─────────────────

@register_tool(
    name="delegate_batch",
    description="Birden çok alt-agent'ı paralel çalıştır. Her birine farklı görev ver.",
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {"type": "string", "default": ""},
                    },
                },
                "description": "Görev listesi: [{\"goal\": \"...\", \"context\": \"...\"}, ...]",
            },
        },
        "required": ["tasks"],
    },
    toolset="delegation",
)
async def delegate_batch_tool(tasks: list[dict]) -> str:
    """Paralel alt-agent çalıştır."""
    from tools.delegate import delegate
    
    ids = delegate.submit_batch(tasks)
    results = []
    for aid in ids:
        result = await delegate.get_result(aid, timeout=120)
        agent = delegate.active.get(aid)
        results.append({
            "agent_id": aid,
            "result": result,
            "status": agent.status if agent else "unknown",
        })
    
    return json.dumps({"results": results}, ensure_ascii=False)


# ─── DEEP RESEARCH ─────────────────────────────────────────

@register_tool(
    name="deep_research",
    description="Derinlemesine web araştırması yap. Çok adımlı arama + sentez.",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Araştırılacak soru/konu",
            },
        },
        "required": ["question"],
    },
    toolset="research",
)
async def deep_research_tool(question: str) -> str:
    """Iteratif deep research başlat (async)."""
    from knowledge.deep_research import DeepResearcher

    researcher = DeepResearcher()
    report = await researcher.research(question)
    stats = researcher.get_stats()

    result = {
        "report": report,
        "stats": stats,
    }
    return json.dumps(result, ensure_ascii=False)


# ─── MCP TOOL CALL ──────────────────────────────────────

@register_tool(
    name="mcp_call_tool",
    description="MCP sunucusundaki bir tool'u çağır.",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Çağrılacak MCP tool adı",
            },
            "arguments": {
                "type": "object",
                "description": "Tool parametreleri",
                "default": {},
            },
        },
        "required": ["tool_name"],
    },
    toolset="mcp",
    check_fn=lambda: False,
)
async def mcp_call_tool_tool(tool_name: str, arguments: dict = None) -> str:
    """MCP tool'unu çağır."""
    from tools.mcp.client import mcp_manager
    args = arguments or {}
    return await mcp_manager.call_tool(tool_name, args)

