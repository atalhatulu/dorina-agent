"""Tool çalıştırma motoru - parametre doğrulama + çalıştırma + hook pipeline."""

from __future__ import annotations
import json
import asyncio
import traceback
from tools.registry import registry, ToolDef
from core.logger import log
from core.event_bus import bus
from core.constants import MAX_TOOL_CALLS_PER_TURN
from core.error_classifier import sanitize_tool_error, classify_api_error, FailoverReason
from hooks.lifecycle import pipeline
from security.approval import approval as _approval
from tools.toolset import get_active_toolsets


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


# ── Recovery hints per FailoverReason ──────────────────────────

_RECOVERY_HINTS: dict[str, dict] = {
    FailoverReason.AUTH: {
        "recoverable": False,
        "hint": "API anahtarini kontrol et veya /setup ile guncelle",
    },
    FailoverReason.AUTH_PERMANENT: {
        "recoverable": False,
        "hint": "API anahtari kalici olarak gecersiz, /setup ile yenile",
    },
    FailoverReason.BILLING: {
        "recoverable": False,
        "hint": "Hesap bakiyeni ve kullanim limitini kontrol et",
    },
    FailoverReason.RATE_LIMIT: {
        "recoverable": True,
        "hint": "Rate limit asildi, birkac saniye bekleyip tekrar dene",
    },
    FailoverReason.UPSTREAM_RATE_LIMIT: {
        "recoverable": True,
        "hint": "Upstream saglayici limitli, /model ile farkli model dene",
    },
    FailoverReason.OVERLOADED: {
        "recoverable": True,
        "hint": "Servis gecici olarak yogun, birkac saniye bekleyip tekrar dene",
    },
    FailoverReason.SERVER_ERROR: {
        "recoverable": True,
        "hint": "Sunucu hatasi, birkac saniye bekleyip tekrar dene",
    },
    FailoverReason.TIMEOUT: {
        "recoverable": True,
        "hint": "Zaman asimi, daha kisa bir islemle tekrar dene",
    },
    FailoverReason.CONTEXT_OVERFLOW: {
        "recoverable": True,
        "hint": "Context cok buyudu, otomatik sikistirma devreye girecek",
    },
    FailoverReason.PAYLOAD_TOO_LARGE: {
        "recoverable": True,
        "hint": "Istek cok buyuk, daha kucuk parcaya bol",
    },
    FailoverReason.MODEL_NOT_FOUND: {
        "recoverable": True,
        "hint": "Model bulunamadi, /model ile farkli model sec",
    },
    FailoverReason.CONTENT_POLICY_BLOCKED: {
        "recoverable": False,
        "hint": "Icerik politikasi engelledi, farkli bir yaklasim dene",
    },
    FailoverReason.FORMAT_ERROR: {
        "recoverable": True,
        "hint": "Format hatasi, sistem otomatik duzeltecek",
    },
    FailoverReason.TOOL_FORMAT_ERROR: {
        "recoverable": True,
        "hint": "Tool format hatasi, mesaj sirasi onarilacak",
    },
    FailoverReason.NETWORK: {
        "recoverable": True,
        "hint": "Baglanti hatasi, birkac saniye bekleyip tekrar dene",
    },
    FailoverReason.TOOL_ERROR: {
        "recoverable": True,
        "hint": "Arac hatasi, parametreleri kontrol et",
    },
    FailoverReason.PARSE_ERROR: {
        "recoverable": True,
        "hint": "Yanit ayristirilamadi, tekrar dene",
    },
}


class ToolExecutor:
    """Tool'ları çağırır, sonuçları toplar."""

    def __init__(self):
        self.call_count = 0
        self._graph_data_available = False  # graphify_query basarili oldu mu?
        self._ALIASES = {"bash": "terminal", "sh": "terminal", "shell": "terminal",
                         "python": "terminal", "cmd": "terminal"}

    # ── Shared setup (used by both sync execute and async_execute) ───────────
    def _setup(self, tool_name: str, arguments: dict) -> tuple[str, ToolDef | None, dict | None, str | None]:
        """Common pre-execution setup.

        Returns (tool_name, tool, resolved_args, error_result).
        error_result is None on success, a JSON string on failure.
        """
        # Tool name aliases
        tool_name = self._ALIASES.get(tool_name, tool_name)

        tool = registry.get(tool_name)
        if not tool:
            return tool_name, None, None, json.dumps({"error": f"Tool bulunamadı: {tool_name}"})

        # ── Graph verisi varken batch_python blokajı ────────────────────
        if self._graph_data_available and tool_name in ("batch_python",):
            msg = "Graphify verisi zaten alindi. batch_python ile tekrar dosya tarama."
            log.debug(f"Graph blokajı: {tool_name} engellendi (graphify zaten calisti)")
            bus.publish("tool:aborted", name=tool_name, reason="graph_data_available")
            return tool_name, None, None, json.dumps({"error": msg, "aborted": True, "hint": "graphify_query sonucunu kullan, ek dosya tarama gerekmez"})

        # Resolve parameters — arguments must already be a dict
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
            return tool_name, None, None, json.dumps({"error": error_msg, "missing_params": missing})

        # ── HOOK: Pre-execution validation (can abort) ──
        bus.publish("tool:executing", name=tool_name, arguments=resolved_args)
        if not pipeline.run_pre_execution(tool_name, resolved_args):
            abort_msg = f"Tool '{tool_name}' pre-execution hook tarafından iptal edildi"
            log.info(abort_msg)
            bus.publish("tool:aborted", name=tool_name, reason="hook_rejected")
            return tool_name, None, None, json.dumps({"error": abort_msg, "aborted": True})

        # ── HOOK: Parameter transformation (can modify) ──
        resolved_args = pipeline.run_param_transform(tool_name, resolved_args)

        # ── Approval check ──
        if _approval.needs_approval(tool_name, resolved_args):
            if not _approval.approve(tool_name, resolved_args):
                denied_msg = f"Tool '{tool_name}' kullanıcı tarafından reddedildi"
                log.info(denied_msg)
                bus.publish("tool:aborted", name=tool_name, reason="user_denied")
                return tool_name, None, None, json.dumps({"error": denied_msg, "aborted": True})

        # Update counter
        self.call_count += 1
        if self.call_count > MAX_TOOL_CALLS_PER_TURN:
            raise ToolError(f"Tur başı max {MAX_TOOL_CALLS_PER_TURN} tool çağrısı aşıldı", tool_name)

        # Fire event
        bus.publish("tool:called", name=tool_name, arguments=resolved_args)

        return tool_name, tool, resolved_args, None

    # ── Shared teardown (post-execution result + error handling) ──────────
    def _finish(self, tool_name: str, resolved_args: dict, result: str) -> str:
        """Post-processing hooks and bus events after successful execution."""
        # ── HOOK: Post-processing (can modify result) ──
        result = pipeline.run_post_processing(tool_name, resolved_args, result)
        bus.publish("tool:completed", name=tool_name, result=result)
        return result

    def _handle_error(self, tool_name: str, error: Exception) -> str:
        """Common error handling for both sync and async paths."""
        import json  # defensive (Python 3.14.6 intermittent namespace edge-case)
        error_sanitized = sanitize_tool_error(str(error))
        bus.publish("tool:error", name=tool_name, error=str(error))
        log.error(
            f"Tool hatası [{tool_name}]: {error}",
            extra={"tool": tool_name, "error_type": type(error).__name__},
        )
        try:
            from core.error_db import log_tool_error
            log_tool_error(
                tool_name=tool_name,
                message=str(error),
                traceback=traceback.format_exc(),
            )
        except ImportError:
            pass

        # Classify and add recovery hints
        classified = classify_api_error(error)
        recovery = _RECOVERY_HINTS.get(classified.reason, {
            "recoverable": True,
            "hint": "Bilinmeyen hata, tekrar dene",
        })
        return json.dumps({
            "error": f"Tool '{tool_name}' hatasi: {classified.reason}",
            "recoverable": recovery["recoverable"],
            "recovery_hint": recovery["hint"],
        })

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, tool_name: str, arguments: dict, timeout: int = 30) -> str:
        """Bir tool'u senkron çağır. Sonucu JSON string döndür.
        arguments bir dict olmalıdır.
        """
        tool_name, tool, resolved_args, err = self._setup(tool_name, arguments)
        if err:
            return err

        # Otomatik toolset aktiflestirme — tool bulundu ama toolset kapaliysa ac
        if tool.toolset and tool.toolset not in get_active_toolsets():
            from tools.toolset import ACTIVE_TOOLSETS
            ACTIVE_TOOLSETS.add(tool.toolset)

        try:
            if tool.is_async:
                import asyncio
                try:
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
                            return json.dumps({"error": f"Async tool '{tool_name}' returned coroutine"})

            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            return self._finish(tool_name, resolved_args, result)

        except ToolError:
            raise
        except Exception as e:
            return self._handle_error(tool_name, e)

    def execute_json(self, tool_name: str, arguments_str: str, timeout: int = 30) -> str:
        """Bir tool'u string JSON argümanla çağır. Önce parse eder, sonra execute()'e yönlendirir."""
        try:
            import re as _re
            args = json.loads(arguments_str)
        except json.JSONDecodeError:
            repaired = arguments_str.strip()
            repaired = _re.sub(r"(?<!\\)'", '"', repaired)
            repaired = _re.sub(r",\s*}", "}", repaired)
            repaired = _re.sub(r",\s*]", "]", repaired)
            try:
                args = json.loads(repaired)
                log.debug(f"execute_json: repaired JSON for '{tool_name}'")
            except json.JSONDecodeError:
                args = {"input": arguments_str}
        return self.execute(tool_name, args, timeout=timeout)

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

    async def async_execute(self, tool_name: str, arguments: dict, timeout: int = 30) -> str:
        """Bir tool'u async çağır. Sonucu JSON string döndür.
        arguments bir dict olmalıdır.
        """
        tool_name, tool, resolved_args, err = self._setup(tool_name, arguments)
        if err:
            return err

        try:
            if tool.is_async:
                result = await tool.handler(**resolved_args)
            else:
                result = await asyncio.to_thread(tool.handler, **resolved_args)
                if type(result).__name__ == "coroutine":
                    result = await result

            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            return self._finish(tool_name, resolved_args, result)

        except ToolError:
            raise
        except Exception as e:
            return self._handle_error(tool_name, e)

    async def async_execute_json(self, tool_name: str, arguments_str: str, timeout: int = 30) -> str:
        """Bir tool'u string JSON argümanla async çağır. Önce parse eder, sonra async_execute()'e yönlendirir."""
        try:
            import re as _re
            args = json.loads(arguments_str)
        except json.JSONDecodeError:
            repaired = arguments_str.strip()
            repaired = _re.sub(r"(?<!\\)'", '"', repaired)
            repaired = _re.sub(r",\s*}", "}", repaired)
            repaired = _re.sub(r",\s*]", "]", repaired)
            try:
                args = json.loads(repaired)
                log.debug(f"async_execute_json: repaired JSON for '{tool_name}'")
            except json.JSONDecodeError:
                args = {"input": arguments_str}
        return await self.async_execute(tool_name, args, timeout=timeout)

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
