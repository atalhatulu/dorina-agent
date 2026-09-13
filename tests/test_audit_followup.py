"""Offline regressions for memory paths, provider recovery and file reads."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.mark.parametrize("name", ["../outside", "/absolute", "..", ".", "a/b", "a\\b", "bad\x00name", "", "   "])
def test_skill_rejects_invalid_names(tmp_path, monkeypatch, name):
    from tools.builtin import memory_tools

    monkeypatch.setattr(memory_tools, "MEMORY_DIR", tmp_path / "memories")
    if name == "/absolute":
        name = str(tmp_path / "outside")
    result = json.loads(memory_tools.save_memory_tool("skill", "note", name=name))
    assert "error" in result
    assert not list(tmp_path.rglob("SKILL.md"))


@pytest.mark.parametrize("target", ["../outside", "/absolute", "invalid"])
def test_memory_rejects_invalid_targets_without_writing(tmp_path, monkeypatch, target):
    from tools.builtin import memory_tools

    monkeypatch.setattr(memory_tools, "MEMORY_DIR", tmp_path / "memories")
    assert "error" in json.loads(memory_tools.save_memory_tool(target, "note"))
    assert "error" in json.loads(memory_tools.read_memory_tool(target))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("target", ["user", "memory"])
def test_memory_normal_targets_still_roundtrip(tmp_path, monkeypatch, target):
    from tools.builtin import memory_tools

    monkeypatch.setattr(memory_tools, "MEMORY_DIR", tmp_path / "memories")
    assert json.loads(memory_tools.save_memory_tool(target, "note"))["success"]
    assert json.loads(memory_tools.read_memory_tool(target))["content"] == "- note\n"


@pytest.mark.parametrize("link_file", [False, True])
@pytest.mark.parametrize("procedural", [False, True])
def test_skill_rejects_symlink_escape(tmp_path, monkeypatch, link_file, procedural):
    from tools.builtin import memory_tools
    from memory.procedural import ProceduralMemory

    root = tmp_path / "skills"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "SKILL.md"
    sentinel.write_text("unchanged")
    if link_file:
        (root / "example").mkdir()
        (root / "example" / "SKILL.md").symlink_to(sentinel)
    else:
        (root / "example").symlink_to(outside, target_is_directory=True)
    if procedural:
        ProceduralMemory(root).save_skill("example", "new note")
    else:
        monkeypatch.setattr(memory_tools, "MEMORY_DIR", tmp_path / "memories")
        result = json.loads(memory_tools.save_memory_tool("skill", "new note", name="example"))
        assert "error" in result
    assert sentinel.read_text() == "unchanged"


def test_skill_save_appends_and_keeps_distinct_names(tmp_path, monkeypatch):
    from tools.builtin import memory_tools

    monkeypatch.setattr(memory_tools, "MEMORY_DIR", tmp_path / "memories")
    for name, content in [("Python Test One", "first"), ("Python Test One", "second"), ("Python Test Two", "separate")]:
        assert json.loads(memory_tools.save_memory_tool("skill", content, name=name))["success"]
    assert (tmp_path / "skills/python-test-one/SKILL.md").read_text() == "- first\n- second\n"
    assert (tmp_path / "skills/python-test-two/SKILL.md").read_text() == "- separate\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("reason_name", ["TOOL_FORMAT_ERROR", "RATE_LIMIT"])
async def test_provider_recovery_is_parsed_once_and_does_not_change_config(streaming, reason_name):
    from orchestrator import reasoning
    from core.error_classifier import FailoverReason

    engine = reasoning.ReasoningEngine()
    config = SimpleNamespace(model=SimpleNamespace(provider="deepseek", default="original", max_tokens=100), save=Mock())
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="recovered", tool_calls=None), finish_reason="stop")], usage=None)
    llm = SimpleNamespace(acompletion=AsyncMock(return_value=response))
    normalized = {"content": "recovered", "tool_calls": [], "_streamed": True}
    messages = [{"role": "user", "content": "hello"}]
    params = {"messages": [{"role": "system", "content": "system"}] + messages, "model": "original"}
    classified = SimpleNamespace(reason=getattr(FailoverReason, reason_name), should_compress=False, should_rotate_credential=False, should_fallback=True)
    with patch.object(reasoning, "settings", config), patch("core.error_classifier.classify_api_error", return_value=classified), patch.object(reasoning.asyncio, "sleep", new_callable=AsyncMock), patch.object(engine, "_get_fallback_chain", return_value=[("deepseek", "fallback")]), patch("providers.keys.keys.get_key", return_value="fake"), patch.object(engine, "_think_stream", new_callable=AsyncMock, return_value=normalized), patch.object(engine, "_parse_response", wraps=engine._parse_response) as parse:
        result = await engine._handle_llm_error(RuntimeError("provider error"), llm, params, "original", params["messages"], Mock() if streaming else None, messages)
    assert result["content"] == "recovered"
    assert parse.call_count == (0 if streaming else 1)
    assert config.model.default == "original"
    assert config.model.provider == "deepseek"
    config.save.assert_not_called()


@pytest.mark.asyncio
async def test_file_reads_keep_pages_and_observe_edits(tmp_path):
    from orchestrator import experimental_loop as module

    path = tmp_path / "example.txt"
    path.write_text("first\nsecond\n")
    loop = module.AgentLoopV2()
    loop._temp_mode = True

    async def read(_name, raw):
        args = json.loads(raw)
        return path.read_text().splitlines()[args["offset"] - 1]

    def call(identifier, offset):
        return {"id": identifier, "function": {"name": "read_file", "arguments": json.dumps({"path": str(path), "offset": offset, "limit": 1})}}

    with patch.object(module, "_display", MagicMock()), patch.object(module, "_status", MagicMock()), patch.object(module.executor, "async_execute_json", side_effect=read) as execute:
        await loop._execute_tools([call("page1", 1), call("page2", 2)])
        path.write_text("updated\nsecond\n")
        await loop._execute_tools([call("updated", 1)])
    results = {m["tool_call_id"]: m["content"] for m in loop.context.get_messages() if m["role"] == "tool"}
    assert results == {"page1": "[read_file] → first", "page2": "[read_file] → second", "updated": "[read_file] → updated"}
    assert execute.await_count == 3
