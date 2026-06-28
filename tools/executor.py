"""Tool çalıştırma motoru - parametre doğrulama + çalıştırma + hook pipeline."""

from __future__ import annotations
import json
import asyncio
import traceback
from tools.registry import registry, ToolDef
from core.logger import log
from core.event_bus import bus
from core.constants import MAX_TOOL_CALLS_PER_TURN
from core.error_classifier import sanitize_tool_error
from hooks.lifecycle import pipeline


class ToolError(Exception):
    """Tool çalıştırma hatası."""
    def __init__(self, message: str, tool_name: str = ""):
        self.tool_name = tool_name
        super().__init__(f"[{tool_name}] {message}")


def _validate_required_params(tool: ToolDef, arguments: dict) -> list[str]:
    """Validate that all required parameters are present in arguments.
    Returns a list of missing parameter names (empty list = valid)."""
    params_schema = tool.parameters
    if not params_schema or not isinstance(params_schema, dict):
        return []
    required = params_schema.get("required", [])
    if not required:
        return []
    # Check for truly missing, None, or empty string values on required params
    # (model sometimes sends path="" which is effectively missing)
    missing = []
    for p in required:
        if p not in arguments:
            missing.append(p)
        elif arguments[p] is None:
            missing.append(p)
        elif isinstance(arguments[p], str) and arguments[p].strip() == "":
            missing.append(p)
    return missing


class ToolExecutor:
    """Tool'ları çağırır, sonuçları toplar."""

    def __init__(self):
        self.call_count = 0

    def execute(self, tool_name: str, arguments: dict | str, timeout: int = 30) -> str:
        """Bir tool'u senkron çağır. Sonucu JSON string döndür.

        Hook pipeline akışı:
          1. bus.publish("tool:executing")
          2. pipeline.run_pre_execution()  → False dönerse tool iptal
          3. pipeline.run_param_transform() → parametreleri değiştirebilir
          4. Tool'u çalıştır
          5. bus.publish("tool:executed") veya bus.publish("tool:aborted")
          6. pipeline.run_post_processing() → sonucu değiştirebilir
        """
        # Tool name aliases
        ALIASES = {"bash": "terminal", "sh": "terminal", "shell": "terminal",
                   "python": "terminal", "cmd": "terminal"}
        tool_name = ALIASES.get(tool_name, tool_name)

        tool = registry.get(tool_name)
        if not tool:
            raise ToolError(f"Tool bulunamadı: {tool_name}", tool_name)

        # Resolve parameters: ensure arguments is a dict with JSON repair
        resolved_args: dict = {}
        if isinstance(arguments, str):
            try:
                resolved_args = json.loads(arguments)
            except json.JSONDecodeError:
                import re as _re
                repaired = arguments.strip()
                repaired = _re.sub(r"(?<!\\)'", '"', repaired)
                repaired = _re.sub(r",\s*}", "}", repaired)
                repaired = _re.sub(r",\s*]", "]", repaired)
                try:
                    resolved_args = json.loads(repaired)
                    log.debug(f"Repaired JSON for '{tool_name}': ...")
                except json.JSONDecodeError:
                    resolved_args = {"input": arguments}
        else:
            resolved_args = arguments

        # ── Validate required parameters BEFORE calling the handler ──
        missing = _validate_required_params(tool, resolved_args)
        if missing:
            error_msg = (
                f"Eksik zorunlu parametreler: {', '.join(missing)}. "
                f"Tool '{tool_name}' için şu parametreler zorunludur: {tool.parameters.get('required', [])}"
            )
            log.debug(f"Parameter validation failed [{tool_name}]: missing={missing}")
            bus.publish("tool:error", name=tool_name, error=error_msg)
            return json.dumps({"error": error_msg, "missing_params": missing})

        # ── HOOK: Pre-execution validation (can abort) ──
        bus.publish("tool:executing", name=tool_name, arguments=resolved_args)
        if not pipeline.run_pre_execution(tool_name, resolved_args):
            abort_msg = f"Tool '{tool_name}' pre-execution hook tarafından iptal edildi"
            log.info(abort_msg)
            bus.publish("tool:aborted", name=tool_name, reason="hook_rejected")
            return json.dumps({"error": abort_msg, "aborted": True})

        # ── HOOK: Parameter transformation (can modify) ──
        resolved_args = pipeline.run_param_transform(tool_name, resolved_args)

        # Update counter
        self.call_count += 1
        if self.call_count > MAX_TOOL_CALLS_PER_TURN:
            raise ToolError(f"Tur başı max {MAX_TOOL_CALLS_PER_TURN} tool çağrısı aşıldı", tool_name)

        # Fire event
        bus.publish("tool:called", name=tool_name, arguments=resolved_args)
        bus.publish("monitoring:tool_called", name=tool_name, arguments=resolved_args)

        # Execute
        try:
            if tool.is_async:
                import asyncio
                try:
                    # Check if there's a running event loop
                    loop = asyncio.get_running_loop()
                    # Running inside an event loop — submit to loop via a thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(asyncio.run, tool.handler(**resolved_args))
                        result = fut.result(timeout=timeout)
                except RuntimeError:
                    # No running event loop
                    result = asyncio.run(tool.handler(**resolved_args))
            else:
                import asyncio as _aio
                import inspect as _ins
                if _ins.iscoroutinefunction(tool.handler):
                    result = _aio.run(tool.handler(**resolved_args))
                else:
                    result = tool.handler(**resolved_args)
                    if type(result).__name__ == "coroutine":
                        try:
                            result = _aio.run(result)
                        except (RuntimeError, TypeError):
                            result = json.dumps({"error": f"Async tool '{tool_name}' returned coroutine"})

            # Convert to string
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)

            # ── HOOK: Post-processing (can modify result) ──
            result = pipeline.run_post_processing(tool_name, resolved_args, result)

            bus.publish("tool:executed", name=tool_name, result=result)
            bus.publish("tool:completed", name=tool_name, result=result)
            bus.publish("monitoring:tool_executed", name=tool_name, result=result, latency_ms=0.0)
            return result

        except Exception as e:
            error_raw = f"Hata: {e}\n{traceback.format_exc()}"
            # Sanitize the error for LLM consumption (strip XML, code fences, truncate)
            error_sanitized = sanitize_tool_error(str(e))
            bus.publish("tool:aborted", name=tool_name, error=str(e))
            bus.publish("tool:error", name=tool_name, error=str(e))
            bus.publish("monitoring:tool_error", name=tool_name, error=str(e))
            log.error(
                f"Tool hatası [{tool_name}]: {e}",
                extra={"tool": tool_name, "error_type": type(e).__name__},
            )
            # Log to error database
            try:
                from core.error_db import log_tool_error
                log_tool_error(
                    tool_name=tool_name,
                    message=str(e),
                    traceback=traceback.format_exc(),
                )
            except Exception:
                pass
            return json.dumps({
                "error": error_sanitized,
            })

    def execute_multi(self, calls: list[dict]) -> list[dict]:
        """Birden çok tool'u sırayla çağır.

        calls: [{"name": "...", "arguments": {...}}, ...]
        """
        results = []
        for call in calls:
            try:
                result = self.execute(call["name"], call.get("arguments", {}))
                results.append({
                    "name": call["name"],
                    "result": result,
                    "error": None,
                })
            except ToolError as e:
                results.append({
                    "name": call["name"],
                    "result": None,
                    "error": str(e),
                })
        return results

    def reset_count(self):
        """Tool çağrı sayacını sıfırla (yeni tur)."""
        self.call_count = 0

    async def async_execute(self, tool_name: str, arguments: dict | str, timeout: int = 30) -> str:
        """Bir tool'u async çağır. Sonucu JSON string döndür.

        Hook pipeline akışı (async versiyon):
          1. bus.publish("tool:executing")
          2. pipeline.run_pre_execution()  → False dönerse tool iptal
          3. pipeline.run_param_transform() → parametreleri değiştirebilir
          4. Async tool'u await ile çalıştır
          5. bus.publish("tool:executed") veya bus.publish("tool:aborted")
          6. pipeline.run_post_processing() → sonucu değiştirebilir
        """
        # Tool name aliases
        ALIASES = {"bash": "terminal", "sh": "terminal", "shell": "terminal",
                   "python": "terminal", "cmd": "terminal"}
        tool_name = ALIASES.get(tool_name, tool_name)

        tool = registry.get(tool_name)
        if not tool:
            raise ToolError(f"Tool bulunamadı: {tool_name}", tool_name)

        # Resolve parameters: ensure arguments is a dict with JSON repair
        resolved_args: dict = {}
        if isinstance(arguments, str):
            try:
                resolved_args = json.loads(arguments)
            except json.JSONDecodeError:
                import re as _re
                repaired = arguments.strip()
                repaired = _re.sub(r"(?<!\\)'", '"', repaired)
                repaired = _re.sub(r",\s*}", "}", repaired)
                repaired = _re.sub(r",\s*]", "]", repaired)
                try:
                    resolved_args = json.loads(repaired)
                    log.debug(f"Repaired JSON for '{tool_name}': ...")
                except json.JSONDecodeError:
                    resolved_args = {"input": arguments}
        else:
            resolved_args = arguments

        # ── Validate required parameters BEFORE calling the handler ──
        missing = _validate_required_params(tool, resolved_args)
        if missing:
            error_msg = (
                f"Eksik zorunlu parametreler: {', '.join(missing)}. "
                f"Tool '{tool_name}' için şu parametreler zorunludur: {tool.parameters.get('required', [])}"
            )
            log.debug(f"Parameter validation failed [{tool_name}]: missing={missing}")
            bus.publish("tool:error", name=tool_name, error=error_msg)
            return json.dumps({"error": error_msg, "missing_params": missing})

        # ── HOOK: Pre-execution validation (can abort) ──
        bus.publish("tool:executing", name=tool_name, arguments=resolved_args)
        if not pipeline.run_pre_execution(tool_name, resolved_args):
            abort_msg = f"Tool '{tool_name}' pre-execution hook tarafından iptal edildi"
            log.info(abort_msg)
            bus.publish("tool:aborted", name=tool_name, reason="hook_rejected")
            return json.dumps({"error": abort_msg, "aborted": True})

        # ── HOOK: Parameter transformation (can modify) ──
        resolved_args = pipeline.run_param_transform(tool_name, resolved_args)

        # Update counter
        self.call_count += 1
        if self.call_count > MAX_TOOL_CALLS_PER_TURN:
            raise ToolError(f"Tur başı max {MAX_TOOL_CALLS_PER_TURN} tool çağrısı aşıldı", tool_name)

        # Fire event
        bus.publish("tool:called", name=tool_name, arguments=resolved_args)
        bus.publish("monitoring:tool_called", name=tool_name, arguments=resolved_args)

        # Execute (async-aware)
        try:
            if tool.is_async:
                result = await tool.handler(**resolved_args)
            else:
                result = await asyncio.to_thread(tool.handler, **resolved_args)
                # Coroutine safety: if handler returned a coroutine, await it
                if type(result).__name__ == "coroutine":
                    result = await result

            # Convert to string
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)

            # ── HOOK: Post-processing (can modify result) ──
            result = pipeline.run_post_processing(tool_name, resolved_args, result)

            bus.publish("tool:executed", name=tool_name, result=result)
            bus.publish("tool:completed", name=tool_name, result=result)
            bus.publish("monitoring:tool_executed", name=tool_name, result=result, latency_ms=0.0)
            return result

        except Exception as e:
            error_raw = f"Hata: {e}\n{traceback.format_exc()}"
            # Sanitize the error for LLM consumption (strip XML, code fences, truncate)
            error_sanitized = sanitize_tool_error(str(e))
            bus.publish("tool:aborted", name=tool_name, error=str(e))
            bus.publish("tool:error", name=tool_name, error=str(e))
            bus.publish("monitoring:tool_error", name=tool_name, error=str(e))
            log.error(
                f"Tool hatası [{tool_name}]: {e}",
                extra={"tool": tool_name, "error_type": type(e).__name__},
            )
            # Log to error database
            try:
                from core.error_db import log_tool_error
                log_tool_error(
                    tool_name=tool_name,
                    message=str(e),
                    traceback=traceback.format_exc(),
                )
            except Exception:
                pass
            return json.dumps({
                "error": error_sanitized,
            })

    async def async_execute_multi(self, calls: list[dict]) -> list[dict]:
        """Birden çok tool'u async sırayla çağır.

        calls: [{"name": "...", "arguments": {...}}, ...]
        """
        results = []
        for call in calls:
            try:
                result = await self.async_execute(call["name"], call.get("arguments", {}))
                results.append({
                    "name": call["name"],
                    "result": result,
                    "error": None,
                })
            except ToolError as e:
                results.append({
                    "name": call["name"],
                    "result": None,
                    "error": str(e),
                })
        return results


executor = ToolExecutor()
