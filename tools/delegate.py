"""
delegate_task / delegate_batch — SubAgent delegasyon sistemi.

Async-native SubAgent'lar. Her sub-agent kendi mini-loop'unu calistirir,
V2 pattern'lerini (error classification, context compression, repair,
self-reflection) kullanir. Thread yok, polling yok.
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
from collections import OrderedDict
from typing import Optional

from core.logger import log
from tools.registry import registry, register_tool
from tools.executor import executor
from tools.toolset import toolset_summary
from core.constants import MAX_TURNS
from orchestrator.reasoning import ReasoningEngine
from orchestrator.compressor import ContextCompressor
from orchestrator.repair import repair_message_sequence
from core.error_classifier import classify_api_error
from core.error_db import log_error_pattern

# Sub-agent kendi alt-agent uretemez — recursive delegation engeli
BLOCKED_TOOLS = frozenset({"delegate_task", "delegate_batch", "mcp_call_tool"})


class SubAgent:
    """Alt-agent: izole baglamda calisan mini bir Dorina.

    V2 pattern'lerini kullanir: error classification, context compression,
    repair_message_sequence, self-reflection, read_file cache.
    """

    def __init__(self, goal: str, context: str = "", toolsets: list[str] = None):
        self.id = uuid.uuid4().hex[:8]
        self.goal = goal
        self.context = context
        self.toolset_names = toolsets or []
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.status = "pending"
        self.turn_count = 0
        self.engine = ReasoningEngine()
        self.compressor = ContextCompressor()
        self._error_patterns: dict[str, int] = {}
        self._read_cache: OrderedDict = OrderedDict()
        self._done = asyncio.Event()

    async def run(self) -> str:
        """Alt-agent'i calistir. Sonucu JSON string dondurur."""
        self.status = "running"
        log.info("SubAgent [%s] basladi: %s", self.id, self.goal[:60])
        try:
            result = await self._async_run()
            self.status = "completed"
            self.result = result
            self._done.set()
            return result
        except Exception as e:
            self.error = str(e)
            self.status = "error"
            log.error("SubAgent [%s] hatasi: %s", self.id, e)
            self._done.set()
            return json.dumps({"error": str(e)})

    # ── read_file cache ──────────────────────────────────────────

    def _cache_get(self, key: str) -> Optional[str]:
        if key in self._read_cache:
            self._read_cache.move_to_end(key)
            return self._read_cache[key]
        return None

    def _cache_set(self, key: str, value: str):
        self._read_cache[key] = value
        self._read_cache.move_to_end(key)
        if len(self._read_cache) > 5:
            self._read_cache.popitem(last=False)

    # ── Summarize callback (for ContextCompressor) ───────────────

    async def _summarize(self, text: str) -> str:
        result = await self.engine.think(
            "You summarize conversations. Be concise.",
            [{"role": "user", "content": text}],
        )
        return result.get("content", text[:500])

    # ── Main loop ────────────────────────────────────────────────

    async def _async_run(self) -> str:
        # System prompt: NO soul injection, but clear tool use instruction
        _tool_names = ", ".join(sorted(
            t.name for t in registry.list()
            if t.toolset in (self.toolset_names or {"file", "web", "terminal"})
        ))
        system = f"Goal: {self.goal}"
        if self.context:
            system += f"\n\nContext: {self.context}"
        system += (
            f"\n\nAvailable tools: {_tool_names}"
            "\n\nCall these tools via function calling to achieve the goal. "
            "Use function_call format, do not fake it with XML or plain text. "
            "Do not answer without calling the tools. "
            "When done, give a direct answer."
        )

        messages = [{"role": "system", "content": system}]

        # Tool secimi — subagent'in kendi toolset'lerinden
        tool_schemas = []
        for t in registry.list():
            if t.toolset in (self.toolset_names or {"file", "web", "terminal"}):
                tool_schemas.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                })

        max_turns = min(MAX_TURNS, 10)
        error_counts: dict[str, int] = {}

        for turn in range(max_turns):
            self.turn_count = turn

            # Cancellation check
            if self.status == "cancelled":
                return json.dumps({"error": "subagent iptal edildi"})

            # Context compression (aggressive threshold)
            if self.compressor.should_compress(messages):
                messages = await self.compressor.compress(
                    messages, self._summarize
                )

            # Think — narrowed exception
            try:
                response = await self.engine.think(
                    system, messages, tool_schemas
                )
            except (
                RuntimeError,
                ConnectionError,
                TimeoutError,
                ValueError,
                json.JSONDecodeError,
            ) as e:
                log.error("SubAgent LLM error [%s]: %s", self.id, e)
                return json.dumps({"error": f"LLM hatasi: {e}"})
            except Exception as e:
                log.error(
                    "SubAgent unexpected LLM error [%s]: %s",
                    self.id, e,
                )
                return json.dumps(
                    {"error": f"Beklenmeyen LLM hatasi: {e}"}
                )

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            # Final answer — no tool calls
            if not tool_calls and content:
                return content

            # Append assistant message
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls,
            })

            # Execute tools
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "{}")
                tool_id = tc.get("id", f"call_{name}")

                # Block recursive delegation
                if name in BLOCKED_TOOLS:
                    messages.append({
                        "role": "tool",
                        "content": json.dumps({
                            "error": "engellendi",
                            "reason": "recursive delegation blocked",
                        }),
                        "name": name,
                        "tool_call_id": tool_id,
                    })
                    continue

                # read_file cache
                if name == "read_file":
                    cache_key = str(args_raw)
                    cached = self._cache_get(cache_key)
                    if cached is not None:
                        messages.append({
                            "role": "tool",
                            "content": cached,
                            "name": name,
                            "tool_call_id": tool_id,
                        })
                        continue

                # Execute — narrowed exception
                try:
                    result = await executor.async_execute_json(
                        name, args_raw
                    )
                except (
                    ValueError,
                    json.JSONDecodeError,
                    RuntimeError,
                    OSError,
                ) as e:
                    classified = classify_api_error(e)
                    log_error_pattern(
                        f"subagent:{name}",
                        classified.reason,
                        str(e),
                    )
                    messages.append({
                        "role": "tool",
                        "content": json.dumps({
                            "error": str(e),
                            "reason": classified.reason,
                        }),
                        "name": name,
                        "tool_call_id": tool_id,
                    })

                    # Self-reflection: 3+ same error → terminate
                    error_counts[name] = error_counts.get(name, 0) + 1
                    if error_counts[name] >= 3:
                        log.warning(
                            "SubAgent [%s] stopping: %s had %d errors",
                            self.id, name, error_counts[name],
                        )
                        return json.dumps({
                            "error": (
                                f"'{name}' ardarda 3 kez hata verdi, "
                                "sub-agent durduruldu"
                            ),
                        })
                    continue
                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "content": json.dumps({"error": str(e)}),
                        "name": name,
                        "tool_call_id": tool_id,
                    })
                    continue

                # Cache successful read_file
                if name == "read_file":
                    self._cache_set(cache_key, result)

                messages.append({
                    "role": "tool",
                    "content": result,
                    "name": name,
                    "tool_call_id": tool_id,
                })

            # repair_message_sequence after each tool turn
            messages = repair_message_sequence(messages)

        return "Maximum number of turns reached."

    async def wait_done(self):
        """Wait for the SubAgent to complete."""
        await self._done.wait()


class DelegateManager:
    """Alt-agent'lari yonetir. Pure async — thread yok, polling yok."""

    def __init__(self):
        self.active: dict[str, SubAgent] = {}

    async def submit_batch_and_wait(
        self, tasks: list[dict], timeout: int = 120
    ) -> list[dict]:
        """Birden cok alt-agent'i paralel calistir ve bekle."""
        agents: list[SubAgent] = []
        for task in tasks:
            agent = SubAgent(
                goal=task.get("goal", ""),
                context=task.get("context", ""),
                toolsets=task.get("toolsets"),
            )
            self.active[agent.id] = agent
            agents.append(agent)

        results = await asyncio.gather(
            *[agent.run() for agent in agents],
            return_exceptions=True,
        )

        output = []
        for agent, result in zip(agents, results):
            if isinstance(result, Exception):
                agent.status = "error"
                agent.error = str(result)
            output.append({
                "id": agent.id,
                "goal": agent.goal[:60],
                "result": agent.result
                or (str(result) if isinstance(result, str) else ""),
                "status": agent.status,
                "error": agent.error,
            })
        return output

    def list_active(self) -> list[dict]:
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
        agent = self.active.get(agent_id)
        if agent:
            agent.status = "cancelled"

    def cleanup(self):
        self.active = {
            k: v
            for k, v in self.active.items()
            if v.status in ("pending", "running")
        }


# ── Module-level DelegateManager instance ──────────────────────────

delegate = DelegateManager()


# ── Tool handlers ──────────────────────────────────────────────

@register_tool(
    name="delegate_task",
    description=(
        "Bir alt-gorevi (sub-task) ayri bir mini-agent'a devret. "
        "Karmasik, uzun surecek islemler icin. Alt-agent kendi "
        "tool'larini kullanir, sonucu ozet olarak dondurur."
    ),
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "Alt-gorevin hedefi (net ve spesifik olmali)"
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Alt-goreve verilecek baglam "
                    "(dosya yollari, onceki sonuclar)"
                ),
                "default": "",
            },
            "toolsets": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "file", "web", "terminal",
                        "git", "memory", "research",
                    ],
                },
                "description": (
                    "Alt-agentin kullanabilecegi tool kategorileri"
                ),
                "default": ["file", "web", "terminal"],
            },
        },
        "required": ["goal"],
    },
    toolset="delegation",
)
async def delegate_task_tool(
    goal: str,
    context: str = "",
    toolsets: list[str] = None,
) -> str:
    """Bir alt-agent olustur, calistir, sonucu dondur."""
    if toolsets is None:
        toolsets = ["file", "web", "terminal"]
    agent = SubAgent(goal=goal, context=context, toolsets=toolsets)
    return await agent.run()


@register_tool(
    name="delegate_batch",
    description=(
        "Birden fazla alt-gorevi paralel calistir. Her alt-gorev "
        "ayri bir mini-agent. Sonuclari toplu dondurur."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {
                            "type": "string",
                            "default": "",
                        },
                        "toolsets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [
                                "file", "web", "terminal",
                            ],
                        },
                    },
                    "required": ["goal"],
                },
                "description": "Paralel calistirilacak gorevler",
            },
            "timeout": {
                "type": "integer",
                "description": "Toplam zaman asimi (saniye)",
                "default": 120,
            },
        },
        "required": ["tasks"],
    },
    toolset="delegation",
)
async def delegate_batch_tool(
    tasks: list[dict],
    timeout: int = 120,
) -> str:
    """Birden cok alt-agent'i paralel calistir."""
    results = await delegate.submit_batch_and_wait(tasks, timeout)
    return json.dumps(results, ensure_ascii=False)
