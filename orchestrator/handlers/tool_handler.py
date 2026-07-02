"""TOOL_CALLING + WAITING_RESULT handlers — dispatch and execute tools."""

from __future__ import annotations
import asyncio
import json
from orchestrator.state_machine import AgentContext
from core.logger import log


async def handle_tool_calling(loop, ctx: AgentContext):
    """TOOL_CALLING: extract tool_calls from last LLM response, build assistant msg."""
    from ui.status_bar import status as _status

    tool_calls = ctx.llm_response.get("tool_calls", [])
    if not tool_calls:
        return

    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("function", {}).get("name", "unknown_tool"),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                },
            }
            for tc in tool_calls
        ],
    }
    loop.context.messages.append(assistant_msg)
    ctx.tool_calls = tool_calls
    _status.add_tool_call()
    if tool_calls:
        tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        _status.set_status(f"tool: {', '.join(tool_names)}")


async def handle_waiting_result(loop, ctx: AgentContext):
    """WAITING_RESULT: execute tools, add results to context. Partial success → auto-resolve."""
    from tools.executor import executor
    from tools.registry import registry
    from ui import display as _display
    from ui.status_bar import status as _status

    from ui.display import console as _disp_con

    tool_calls = ctx.tool_calls
    if not tool_calls:
        ctx.metadata["all_tools_failed"] = True
        return

    # ── Enforce tool call limits per turn (max 3) ──
    # 15 idi ama LLM gereksiz paralel çağrı yapıp token şişiriyor.
    # 3 tool ile LLM'i seçici olmaya zorla — kritik olmayanı sonraki tura bırakır.
    if len(tool_calls) > 3:
        _trimmed = tool_calls[3:]
        _trimmed_names = [tc.get("function", {}).get("name", "?") for tc in _trimmed]
        _disp_con.print(f"[bold yellow]⚠ Tek turda max 3 tool ({len(tool_calls)} istendi). Ilk 3 calisiyor.[/]")
        tool_calls = tool_calls[:3]
        # Kırpılan tool'ları LLM'e bildir — kafası karışmasın
        loop.context.add_assistant_message(
            f"[SISTEM] {len(_trimmed_names)} tool kırpıldı (limit: 3/tur): {', '.join(_trimmed_names)}. "
            f"Kalanları sonraki turda çağırabilirsin."
        )

    # ── Repetition guard: same file read >1x per turn → skip ──
    import json as _fj
    _seen_in_turn: set = set()
    _filtered: list = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        _key = ""
        if name == "read_file":
            try:
                _args = _fj.loads(fn.get("arguments", "{}"))
                _key = _args.get("path", "")
                if _key in _seen_in_turn:
                    _disp_con.print(f"[dim]⚠ {_key} ayni turda 2. kez okunuyor, atlandi[/]")
                    continue
                _seen_in_turn.add(_key)
            except Exception:
                pass
        _filtered.append(tc)
    tool_calls = _filtered

    READ_TOOLS = frozenset({"read_file", "search_files", "web_search", "web_fetch",
                            "browser_snapshot", "gif_search", "list_directory"})
    read_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") in READ_TOOLS]
    write_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name", "") not in READ_TOOLS]

    success_count = 0
    fail_count = 0

    async def _run_one(tc):
        nonlocal success_count, fail_count
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", "{}")
        tool_call_id = tc.get("id", f"call_{name}")
        _status.add_tool_call()
        from ui.display import flush_stream as _flush_stream
        _flush_stream()
        # Argumanlari coz ve goster (token tahmini icin)
        _fn = tc.get("function", {})
        _raw_args = _fn.get("arguments", "{}")
        try:
            _parsed = json.loads(_raw_args) if isinstance(_raw_args, str) else _raw_args
        except Exception as _parse_e:
            log.warning("Tool arg parse warning [%s]: %s", name, _parse_e)
            _parsed = None
        _display.print_tool_start(name, _parsed)
        try:
            result = await asyncio.to_thread(executor.execute, name, args)
            # Tool ciktisini contexte ekle: read_file disindaki buyuk ciktilar 1500'de kesilir
            _ctx_result = result
            if name != "read_file" and len(_ctx_result) > 2000:
                _ctx_result = _ctx_result[:1500] + f"\n[...{len(_ctx_result)-1500} karakter kisaltildi]"
            loop.context.add_tool_result(name, _ctx_result, tool_call_id)
            if "error" in result[:20].lower():
                _display.print_tool_error(name, result)
                fail_count += 1
            else:
                _display.print_tool_done(name, result)
                # Tool sonrasi session kaydet (temp modda kaydetme)
                if not loop._temp_mode:
                    try:
                        from session.manager import manager as _sm
                        from core.config import settings as _st
                        if _st.session.auto_save:
                            _sm.save(loop.context.get_messages(), summary=f"[{name}] {result[:100]}")
                    except Exception:
                        pass
                success_count += 1
        except Exception as e:
            ctx.metadata["has_error"] = True
            loop._handle_tool_error(name, e, tool_call_id)
            fail_count += 1

    # Read tools in parallel, write tools sequentially
    if read_calls:
        await asyncio.gather(*[_run_one(tc) for tc in read_calls])
    for tc in write_calls:
        await _run_one(tc)

    ctx.metadata["all_tools_failed"] = (success_count == 0 and fail_count > 0)
    ctx.metadata["tool_call_count"] = ctx.metadata.get("tool_call_count", 0) + success_count + fail_count
    # Tools calistiysa THINKING'e don, SYNTHESIZE'i atla
    ctx.metadata["more_tools"] = success_count > 0

    # P2-14: Auto-dependency resolution — if all tools failed, try to find and install missing deps
    if fail_count > 0 and success_count == 0:
        try:
            _error_msgs = []
            for m in loop.context.get_messages()[-fail_count * 2:]:
                if m.get("role") == "tool":
                    _error_msgs.append(str(m.get("content", ""))[:200])
            if _error_msgs:
                _search_query = " ".join(_error_msgs[-2:])[:200]
                _search_result = await asyncio.to_thread(
                    executor.execute, "web_search",
                    '{"query": "' + _search_query.replace('"', "'") + '"}'
                )
                _install_cmd = None
                for _kw in ["pip install", "apt install", "pacman -S", "npm install",
                            "brew install", "cargo install", "dnf install", "yay -S"]:
                    if _kw in _search_result.lower():
                        import re as _re
                        _match = _re.search(r'(' + _kw + r'[^\n.]*)', _search_result)
                        if _match:
                            _install_cmd = _match.group(1).strip()
                            break
                if _install_cmd:
                    _display.print_info(f"Kurulum: {_install_cmd}")
                    executor.execute("terminal", '{"command": "' + _install_cmd.replace('"', "'") + '"}')
                    ctx.metadata["auto_repaired"] = True
                    log.info(f"Auto-resolved: {_install_cmd}")
        except Exception as _dep_e:
            log.debug(f"Auto-dependency resolution failed: {_dep_e}")

    # P2-13: Auto-checkpoint
    from orchestrator.checkpoint import checkpoint_manager as _cp
    _cp.update_turn(ctx.turn)
    if _cp.should_checkpoint:
        await _cp.save(
            {"turn": ctx.turn, "state": "thinking", "messages": loop.context.get_messages()},
            cp_type="auto",
        )
