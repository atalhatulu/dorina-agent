"""RAG-based tool selector — dynamically picks relevant tools for each turn.

Reduces token usage by sending only ~7 relevant tool schemas instead of all 56.

Architecture:
  - Index: tool descriptions stored in ChromaDB (semantic memory) at startup
  - Select: user input → vector search → top N relevant tools
  - Filter: always include critical tools + selected tools
  - Fallback: semantic memory unavailable → return all tools
"""

from __future__ import annotations
from typing import Optional
from core.logger import log

# Critical tools always included regardless of context
ALWAYS_INCLUDE = frozenset({
    "read_file", "write_file", "patch", "terminal", "search_files",
    "web_search", "web_fetch",
})

# Tools that should never be auto-selected (internal/system)
NEVER_SELECT = frozenset({
    "delegate_task", "mcp_call_tool", "plan_and_execute",
})

# Max tools to return per query
DEFAULT_TOP_K = 7

_sem_instance = None


def _get_sem():
    global _sem_instance
    if _sem_instance is None:
        from memory.semantic import SemanticMemory
        _sem_instance = SemanticMemory()
    return _sem_instance


class ToolSelector:
    """Selects relevant tools for the current context using semantic search."""

    def __init__(self):
        self._indexed = False
        self._total_tools = 0

    async def initialize(self):
        """Index all registered tools into semantic memory."""
        from tools.registry import registry

        sem = _get_sem()
        if not hasattr(sem, '_ready') or not sem._ready:
            await sem.initialize()

        if not sem._ready:
            log.warning("Semantic memory unavailable, tool selection disabled")
            self._indexed = False
            return

        tools = registry.list()
        self._total_tools = len(tools)
        count = 0

        for tool in tools:
            if tool.name in NEVER_SELECT:
                continue
            param_names = list(tool.parameters.get("properties", {}).keys())
            search_text = (
                f"Tool: {tool.name}. "
                f"Description: {tool.description}. "
                f"Parameters: {', '.join(param_names)}."
            )
            sem.add(search_text, {
                "tool_name": tool.name,
                "toolset": tool.toolset,
            }, doc_id=f"tool_{tool.name}")
            count += 1

        self._indexed = True
        log.info(f"ToolSelector indexed {count}/{self._total_tools} tools")

    async def select(self, context: str, top_k: int = DEFAULT_TOP_K) -> list[str]:
        """Select relevant tool names for the given context."""
        sem = _get_sem()

        selected = list(ALWAYS_INCLUDE)

        if not self._indexed or not sem._ready:
            log.debug("ToolSelector unavailable, returning all available tools as fallback")
            from tools.registry import registry
            return registry.available_tools()

        results = sem.search(context, n_results=top_k + len(ALWAYS_INCLUDE))

        for item in results:
            meta = item.get("metadata", {})
            name = meta.get("tool_name", "")
            if name and name not in selected and name not in NEVER_SELECT:
                selected.append(name)

        log.debug(f"ToolSelector: selected {len(selected)} tools for '{context[:40]}...'")
        return selected

    def schemas_for(self, tool_names: list[str]) -> list[dict]:
        """Build schema dicts for the given tool names."""
        from tools.registry import registry
        schemas = []
        for name in tool_names:
            tool = registry.get(name)
            if tool and (tool.check_fn is None or tool.check_fn()):
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                })
        return schemas

    async def schemas_for_context(self, context: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
        """One-shot: select + build schemas for context."""
        tool_names = await self.select(context, top_k)
        return self.schemas_for(tool_names)

    def reset(self):
        self._indexed = False
        self._total_tools = 0


selector = ToolSelector()
