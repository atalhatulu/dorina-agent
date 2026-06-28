"""RAG-based tool selector — dynamically picks relevant tools for each turn.

Reduces token usage by sending only ~7 relevant tool schemas instead of all 56.

Architecture:
  - Index: tool descriptions stored in ChromaDB (semantic memory) at startup
  - Select: user input → vector search → top N relevant tools
  - Filter: always include critical tools + selected tools
  - Fallback: semantic memory unavailable → return all tools
"""

from __future__ import annotations
import time as _time
from pathlib import Path
from core.logger import log

ALWAYS_INCLUDE = frozenset({
    "read_file", "write_file", "patch", "terminal", "search_files",
    "web_search", "web_fetch",
})

NEVER_SELECT = frozenset({
    "delegate_task", "mcp_call_tool", "plan_and_execute",
})

DEFAULT_TOP_K = 7

_sem_instance = None
_cache = {"time": 0, "tools": [], "context": ""}
_CACHE_TTL = 60  # 60 saniye cache


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
        
        # Skills index
        self._index_skills(sem)
    
    def _index_skills(self, sem):
        """Index all learned skills into semantic memory."""
        _skills_dir = Path.home() / ".dorina" / "skills"
        if not _skills_dir.exists():
            return
        _sk_count = 0
        for _folder in sorted(_skills_dir.iterdir()):
            if _folder.is_dir():
                _sk = _folder / "SKILL.md"
                if _sk.exists():
                    _content = _sk.read_text(encoding="utf-8").strip()
                    sem.add(f"Skill: {_folder.name}. {_content}", {
                        "skill_name": _folder.name,
                        "type": "skill",
                    }, doc_id=f"skill_{_folder.name}")
                    _sk_count += 1
        if _sk_count:
            log.info(f"ToolSelector indexed {_sk_count} skills")

    async def select(self, context: str, top_k: int = DEFAULT_TOP_K) -> list[str]:
        global _cache
        now = _time.time()
        if _cache["tools"] and _cache["context"] == context and (now - _cache["time"]) < _CACHE_TTL:
            return _cache["tools"]

        sem = _get_sem()
        selected = list(ALWAYS_INCLUDE)

        if not self._indexed or not sem._ready:
            log.debug("ToolSelector unavailable, fallback to all tools")
            from tools.registry import registry
            return registry.available_tools()

        results = sem.search(context, n_results=top_k + len(ALWAYS_INCLUDE))

        for item in results:
            meta = item.get("metadata", {})
            name = meta.get("tool_name", "")
            if name and name not in selected and name not in NEVER_SELECT:
                selected.append(name)

        _cache = {"time": now, "tools": selected, "context": context}
        log.debug(f"ToolSelector: selected {len(selected)} tools")
        return selected

    async def select_skills(self, context: str, top_k: int = 3) -> list[dict]:
        """Context'e gore ilgili skill'leri sec. (tool seciminden bagimsiz)"""
        sem = _get_sem()
        if not self._indexed or not sem._ready:
            return []
        results = sem.search(context, n_results=top_k)
        skills = []
        for item in results:
            meta = item.get("metadata", {})
            if meta.get("type") == "skill":
                skills.append({
                    "name": meta.get("skill_name", ""),
                    "content": item.get("content", ""),
                })
        return skills
    
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
