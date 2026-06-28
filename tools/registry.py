"""Tool kayıt sistemi - tüm tool'lar burada kayıtlı.

Her tool: {name, description, parameters: schema, handler: callable}
"""

from __future__ import annotations
from typing import Callable, Any
from dataclasses import dataclass, field
from core.logger import log
from core.event_bus import bus
from hooks.lifecycle import pipeline


@dataclass
class ToolDef:
    """Bir tool'un tanımı."""
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable
    toolset: str = "default"
    requires_env: list[str] = field(default_factory=list)
    check_fn: Callable | None = None  # Döndürülebilir mi kontrolü
    is_async: bool = False


class ToolRegistry:
    """Tool'ların kayıt defteri + hook yönetimi."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    # ── Tool kayıt / kaldırma ──────────────────────────────────

    def register(self, tool: ToolDef):
        """Tool kaydet."""
        self._tools[tool.name] = tool
        bus.publish("tool:registered", name=tool.name, toolset=tool.toolset)
        log.debug(f"Tool kaydedildi: {tool.name} [{tool.toolset}]")

    def unregister(self, name: str):
        """Tool kaldır."""
        self._tools.pop(name, None)
        bus.publish("tool:unregistered", name=name)

    def get(self, name: str) -> ToolDef | None:
        """İsme göre tool bul."""
        return self._tools.get(name)

    def list(self, toolset: str | None = None) -> list[ToolDef]:
        """Tool'ları listele. İsteğe bağlı toolset filtresi."""
        if toolset:
            return [t for t in self._tools.values() if t.toolset == toolset]
        return list(self._tools.values())

    def schemas(self, toolset: str | None = None) -> list[dict]:
        """LLM'e göndermek için JSON schema listesi."""
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
            if t.check_fn is None or t.check_fn()
        ]

    def available_tools(self) -> list[str]:
        """Kullanılabilecek tool isimleri."""
        return [
            t.name for t in self._tools.values()
            if t.check_fn is None or t.check_fn()
        ]

    def count(self) -> int:
        return len(self._tools)

    # ── Hook yönetimi (pipeline üzerinden) ────────────────────

    def register_hook(self, stage: str, callback: Callable):
        """Tool pipeline'ına hook ekle.

        Args:
            stage: "pre_execution" | "param_transform" | "post_processing"
            callback: Hook fonksiyonu
        """
        pipeline.register(stage, callback)
        log.info(f"Hook kaydedildi: stage={stage}, callback={callback.__name__}")

    def unregister_hook(self, stage: str, callback: Callable):
        """Tool pipeline'ından hook kaldır."""
        pipeline.unregister(stage, callback)
        log.info(f"Hook kaldırıldı: stage={stage}, callback={callback.__name__}")

    def list_hooks(self) -> dict[str, list[str]]:
        """Tüm kayıtlı hook'ları listele."""
        return pipeline.list_hooks()

    def hook_count(self, stage: str | None = None) -> int:
        """Hook sayısını döndür."""
        return pipeline.stage_count(stage)

    def clear_hooks(self, stage: str | None = None):
        """Hook'ları temizle."""
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
    """Decorator ile tool kaydetme.

    Kullanım:
        @register_tool(name="x", description="...", parameters={...})
        def my_tool(param1: str) -> str: ...

    Async fonksiyonlar otomatik algılanır (is_async=True).
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
