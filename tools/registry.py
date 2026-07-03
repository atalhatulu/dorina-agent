"""Tool registry — every tool is registered here.

Each tool: {name, description, parameters: schema, handler: callable}
"""

from __future__ import annotations
from typing import Callable, Any
from dataclasses import dataclass, field
from core.logger import log
from core.event_bus import bus
from hooks.lifecycle import pipeline


@dataclass
class ToolDef:
    """Definition of a single tool."""
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable
    toolset: str = "default"
    requires_env: list[str] = field(default_factory=list)
    check_fn: Callable | None = None  # Availability check
    is_async: bool = False


class ToolRegistry:
    """Tool registry + hook management."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    # ── Register / unregister ─────────────────────────────────

    def register(self, tool: ToolDef):
        """Register a tool."""
        self._tools[tool.name] = tool
        bus.publish("tool:registered", name=tool.name, toolset=tool.toolset)
        log.debug(f"Tool registered: {tool.name} [{tool.toolset}]")

    def unregister(self, name: str):
        """Remove a tool."""
        self._tools.pop(name, None)
        bus.publish("tool:unregistered", name=name)

    def get(self, name: str) -> ToolDef | None:
        """Find a tool by name."""
        return self._tools.get(name)

    def list(self, toolset: str | None = None) -> list[ToolDef]:
        """List tools. Optional toolset filter."""
        if toolset:
            return [t for t in self._tools.values() if t.toolset == toolset]
        return list(self._tools.values())

    def schemas(self, toolset: str | None = None) -> list[dict]:
        """Return JSON schema list for the LLM (filtered by toolset)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self.list(toolset)
        ]

    def schemas_for(self, names: list[str]) -> list[dict]:
        """Return schemas only for the specified tool names."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for name in names
            if (t := self._tools.get(name))
        ]

    def available_tools(self) -> list[str]:
        """Return names of available tools."""
        return [
            t.name for t in self._tools.values()
            if t.check_fn is None or t.check_fn()
        ]

    def count(self) -> int:
        return len(self._tools)

    # ── Hook management (via pipeline) ────────────────────────

    def register_hook(self, stage: str, callback: Callable):
        """Add a hook to the tool pipeline.

        Args:
            stage: "pre_execution" | "param_transform" | "post_processing"
            callback: Hook function
        """
        pipeline.register(stage, callback)
        log.info(f"Hook registered: stage={stage}, callback={callback.__name__}")

    def unregister_hook(self, stage: str, callback: Callable):
        """Remove a hook from the tool pipeline."""
        pipeline.unregister(stage, callback)
        log.info(f"Hook unregistered: stage={stage}, callback={callback.__name__}")

    def list_hooks(self) -> dict[str, list[str]]:
        """List all registered hooks."""
        return pipeline.list_hooks()

    def hook_count(self, stage: str | None = None) -> int:
        """Return the number of hooks."""
        return pipeline.stage_count(stage)

    def clear_hooks(self, stage: str | None = None):
        """Clear all hooks."""
        pipeline.unregister_all(stage)


# Global registry
registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: dict,
    toolset: str = "default",
    requires_env: list[str] | None = None,
    check_fn: Callable | None = None,
):
    """Decorator-based tool registration.

    Usage:
        @register_tool(name="x", description="...", parameters={...})
        def my_tool(param1: str) -> str: ...

    Async functions are auto-detected (is_async=True).
    """
    import inspect as _inspect
    def decorator(handler: Callable) -> Callable:
        tool = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            toolset=toolset,
            requires_env=requires_env or [],
            check_fn=check_fn,
            is_async=_inspect.iscoroutinefunction(handler),
        )
        registry.register(tool)
        return handler
    return decorator
