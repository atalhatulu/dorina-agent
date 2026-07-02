"""
delegate_task — Alt-agent çağırma sistemi.

Bir alt-agent oluşturur, izole context + tool seti ile çalıştırır,
sonucu özet olarak döndürür. Paralel çalıştırma desteği.

Her sub-agent kendi izole thread'inde çalışır, asyncio.run() ile
event loop yönetimini Python'a bırakır. ThreadPoolExecutor paylaşılmaz.
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from core.logger import log
from tools.registry import registry
from tools.executor import executor
from soul.personality import soul
from core.constants import MAX_TURNS

BLOCKED_TOOLS = frozenset(["delegate_task", "mcp_call_tool"])


class SubAgent:
    """Alt-agent: izole bağlamda çalışan mini bir Dorina."""

    def __init__(self, goal: str, context: str = "", toolsets: list[str] = None):
        self.id = uuid.uuid4().hex[:8]
        self.goal = goal
        self.context = context
        self.toolset_names = toolsets or []
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.status = "pending"
        self.turn_count = 0

    def run(self) -> str:
        """Alt-agent'ı çalıştır. Thread pool içinde çağrılır.
        asyncio.run() ile temiz bir event loop yönetimi sağlar."""
        self.status = "running"
        log.info(f"SubAgent [{self.id}] basladi: {self.goal[:60]}")

        try:
            result = asyncio.run(self._async_run())
            self.status = "completed"
            self.result = result
            return result
        except Exception as e:
            self.error = str(e)
            self.status = "error"
            log.error(f"SubAgent [{self.id}] hatasi: {e}")
            return json.dumps({"error": str(e)})

    async def _async_run(self) -> str:
        """Async iç mantık — asyncio.run() ile sarılır."""
        available = [t for t in registry.available_tools() if t not in BLOCKED_TOOLS]

        system = (
            f"{soul.system_prompt}\n\nGörev: {self.goal}\n\nBağlam: {self.context}"
            if self.context
            else f"{soul.system_prompt}\n\nGörev: {self.goal}"
        )

        messages = [{"role": "system", "content": system}]

        from orchestrator.reasoning import ReasoningEngine
        engine = ReasoningEngine()

        max_iter = min(MAX_TURNS, 15)
        for turn in range(max_iter):
            self.turn_count = turn

            response = await engine.think(
                system_prompt=system,
                messages=messages,
                tools=[
                    t for t in registry.schemas()
                    if t["function"]["name"] in available
                ],
            )

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            if not tool_calls and content:
                return content

            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "{}")
                tool_id = tc.get("id", f"call_{name}")

                if name in BLOCKED_TOOLS:
                    messages.append({
                        "role": "tool",
                        "content": json.dumps({"error": "engellendi"}),
                        "name": name,
                        "tool_call_id": tool_id,
                    })
                    continue

                result = await executor.async_execute_json(name, args)
                messages.append({
                    "role": "tool",
                    "content": result,
                    "name": name,
                    "tool_call_id": tool_id,
                })

        return "Maksimum tur sayısına ulaşıldı."


class DelegateManager:
    """Alt-agent'ları yönetir. Her agent kendi izole executor'ında."""

    def __init__(self):
        self.active: dict[str, SubAgent] = {}
        self._lock = threading.Lock()

    def submit(self, goal: str, context: str = "", toolsets: list[str] = None) -> str:
        """Alt-agent gönder. Her agent kendi thread'inde çalışır."""
        agent = SubAgent(goal, context, toolsets)
        with self._lock:
            self.active[agent.id] = agent
        _exec = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"subagent-{agent.id}"
        )
        _exec.submit(self._run_and_store, agent, _exec)
        return agent.id

    def submit_batch(self, tasks: list[dict]) -> list[str]:
        ids = []
        for task in tasks:
            aid = self.submit(
                goal=task.get("goal", ""),
                context=task.get("context", ""),
                toolsets=task.get("toolsets"),
            )
            ids.append(aid)
        return ids

    async def submit_batch_and_wait(
        self, tasks: list[dict], timeout: int = 120
    ) -> list[dict]:
        ids = self.submit_batch(tasks)
        deadline = time.time() + timeout
        results = []
        for aid in ids:
            remaining = max(0, int(deadline - time.time()))
            result = await self.get_result(aid, timeout=remaining)
            with self._lock:
                agent = self.active.get(aid)
            results.append({
                "id": aid,
                "goal": agent.goal if agent else "unknown",
                "result": result,
                "status": agent.status if agent else "unknown",
                "error": agent.error if agent else None,
            })
        return results

    async def get_results_batch(
        self, agent_ids: list[str], timeout: int = 30
    ) -> list[dict]:
        deadline = time.time() + timeout
        results = []
        for aid in agent_ids:
            remaining = max(0, int(deadline - time.time()))
            result = await self.get_result(aid, timeout=remaining)
            with self._lock:
                agent = self.active.get(aid)
            results.append({
                "id": aid,
                "result": result,
                "status": agent.status if agent else "unknown",
                "error": agent.error if agent else None,
            })
        return results

    def _run_and_store(self, agent: SubAgent, exec_ref: ThreadPoolExecutor):
        try:
            agent.run()
        finally:
            exec_ref.shutdown(wait=False)

    async def get_result(self, agent_id: str, timeout: int = 120) -> Optional[str]:
        with self._lock:
            agent = self.active.get(agent_id)
        if not agent:
            return None

        start = time.time()
        while agent.status in ("pending", "running"):
            if time.time() - start > timeout:
                agent.status = "timeout"
                return json.dumps({"error": "timeout"})
            await asyncio.sleep(0.1)

        return agent.result

    def list_active(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": a.id,
                    "goal": a.goal[:50],
                    "status": a.status,
                    "turns": a.turn_count,
                }
                for a in self.active.values()
                if a.status in ("pending", "running")
            ]

    def cancel(self, agent_id: str):
        with self._lock:
            agent = self.active.get(agent_id)
            if agent:
                agent.status = "cancelled"

    def cleanup(self):
        with self._lock:
            self.active = {
                k: v
                for k, v in self.active.items()
                if v.status in ("pending", "running")
            }


delegate = DelegateManager()
