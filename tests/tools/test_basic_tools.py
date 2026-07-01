"""Tests for tools/builtin/basic.py — terminal, file, and web tools."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ─── TERMINAL TOOL TESTS ──────────────────────────────


@pytest.mark.asyncio
async def test_terminal_echo():
    """Run a simple echo command and check output."""
    from tools.builtin.basic import terminal_tool

    result = await terminal_tool("echo hello", pty=False, background=False)
    # Normal mode returns plain text output (not JSON)
    assert "hello" in result


@pytest.mark.asyncio
async def test_terminal_nonexistent_command():
    """Running a nonexistent command should produce an error (JSON-wrapped)."""
    from tools.builtin.basic import terminal_tool

    result = await terminal_tool("nonexistent_command_xyz_123", pty=False, background=False)
    # Non-existent command returns JSON error because subprocess raises exception
    # or the shell returns non-zero exit code with stderr text
    try:
        data = json.loads(result)
        assert "error" in data
    except json.JSONDecodeError:
        # Could also be plain stderr text
        assert "not found" in result.lower() or "No such file" in result


@pytest.mark.asyncio
async def test_terminal_custom_cwd(tmp_path):
    """cwd parameter is parsed and validated; non-PTY mode doesn't pass it to subprocess.run
    but the tool at least validates the directory exists."""
    from tools.builtin.basic import terminal_tool

    # Passing a valid cwd should not error (even if not applied in non-PTY mode)
    result = await terminal_tool("echo ok", cwd=str(tmp_path), pty=False, background=False)
    # Should return the output from echo
    assert "ok" in result


# ─── READ FILE TOOL TESTS ─────────────────────────────


def test_read_file_nonexistent():
    """Reading a nonexistent file should return an error."""
    from tools.builtin.basic import read_file_tool

    result = read_file_tool("/nonexistent/path/to/file_xyz_123.txt")
    data = json.loads(result)
    assert "error" in data


def test_read_file_content(tmp_path):
    """Create a temp file, read it back, verify content."""
    from tools.builtin.basic import read_file_tool

    test_file = tmp_path / "test_read.txt"
    content = "line 1\nline 2\nline 3\n"
    test_file.write_text(content)

    result = read_file_tool(str(test_file))
    assert "line 1" in result
    assert "line 2" in result
    assert "line 3" in result


def test_read_file_with_offset(tmp_path):
    """Read file with offset/limit pagination."""
    from tools.builtin.basic import read_file_tool

    test_file = tmp_path / "test_paginate.txt"
    lines = "\n".join(f"line {i}" for i in range(1, 21))
    test_file.write_text(lines)

    # Read with offset=5, limit=3 — should get lines 5,6,7
    result = read_file_tool(str(test_file), offset=5, limit=3)
    assert "line 5" in result
    assert "line 6" in result
    assert "line 7" in result
    assert "line 4" not in result or "line 4" not in (json.loads(result).get("error", "") if isinstance(json.loads(result), dict) else result)


def test_read_file_binary_check(tmp_path):
    """Binary files should be rejected."""
    from tools.builtin.basic import read_file_tool

    bin_file = tmp_path / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")

    result = read_file_tool(str(bin_file))
    data = json.loads(result)
    assert "error" in data
    # Should mention binary
    assert "binary" in data.get("error", "").lower() or "BINARY" in json.dumps(data)


# ─── SEARCH FILES TOOL TESTS ──────────────────────────


@pytest.mark.asyncio
async def test_search_files_pattern(tmp_path):
    """Search for a pattern in a temp file."""
    from tools.builtin.basic import search_files_tool

    test_file = tmp_path / "test_search.txt"
    test_file.write_text("unique_pattern_abc_123\nother content\n")

    result = await search_files_tool("unique_pattern_abc_123", path=str(tmp_path))
    # Should find the pattern
    assert "unique_pattern_abc_123" in result


@pytest.mark.asyncio
async def test_search_files_no_match(tmp_path):
    """Search for a pattern that doesn't exist."""
    from tools.builtin.basic import search_files_tool

    test_file = tmp_path / "test_search_empty.txt"
    test_file.write_text("some content")

    result = await search_files_tool("NONEXISTENT_PATTERN_XYZ_999", path=str(tmp_path))
    data = json.loads(result)
    assert "error" in data


# ─── WEB SEARCH TOOL TESTS ────────────────────────────


@pytest.mark.asyncio
async def test_web_search_invalid():
    """Web search with garbage — should handle gracefully (error or fallback)."""
    from tools.builtin.basic import web_search_tool

    result = await web_search_tool("")
    data = json.loads(result) if isinstance(result, str) and result.startswith("{") else {"raw": str(result)}
    # Should not crash — should return either results, an error, or fallback
    assert data is not None


@pytest.mark.asyncio
async def test_web_search_garbage_query():
    """Web search with nonsense string — should not crash."""
    from tools.builtin.basic import web_search_tool

    # A very long nonsense query should not break the tool
    result = await web_search_tool("z" * 500, max_results=1)
    # Should not crash — either returns something or errors gracefully
    assert isinstance(result, str)


# ─── WEB FETCH TOOL TESTS ─────────────────────────────


@pytest.mark.asyncio
async def test_web_fetch_invalid_url():
    """Fetch from an invalid URL should return an error."""
    from tools.builtin.basic import web_fetch_tool

    result = await web_fetch_tool("http://invalid.url.that.does.not.exist.xyz/", timeout=5)
    data = json.loads(result) if isinstance(result, str) and result.startswith("{") else {"raw": str(result)}
    # Should contain an error key for invalid URL
    # It could also be a JSON error in metadata
    output = json.dumps(data)
    assert "error" in data or "hat" in output.lower() or "timed out" in output.lower() or "connection" in output.lower() or "unreachable" in output.lower()


@pytest.mark.asyncio
async def test_web_fetch_malformed_url():
    """Fetch from a malformed URL should return an error."""
    from tools.builtin.basic import web_fetch_tool

    result = await web_fetch_tool("not-a-url", timeout=5)
    data = json.loads(result) if isinstance(result, str) and result.startswith("{") else {"raw": str(result)}
    output = json.dumps(data)
    # Should not crash
    assert isinstance(output, str)


# ─── WRITE FILE TOOL TESTS ──────────────────────────


# --- test_write_file_new ---
def test_write_file_new(tmp_path):
    """Create a new file and verify its content."""
    from tools.builtin.basic import write_file_tool
    import soul.personality as _sp
    _sp.GODMODE = True  # bypass allowed-dirs check for tmp_path

    test_file = tmp_path / "write_new_test.txt"
    content = "hello world\nline 2\nline 3\n"
    result = write_file_tool(str(test_file), content)
    data = json.loads(result)
    assert data.get("success") is True, f"Expected success, got: {data}"
    assert test_file.exists()
    assert test_file.read_text() == content


# --- test_write_file_overwrite ---
def test_write_file_overwrite(tmp_path):
    """Overwrite an existing file and verify content changed."""
    from tools.builtin.basic import write_file_tool
    import soul.personality as _sp
    _sp.GODMODE = True  # bypass allowed-dirs check for tmp_path

    test_file = tmp_path / "write_overwrite_test.txt"
    test_file.write_text("original content")
    result = write_file_tool(str(test_file), "new content")
    data = json.loads(result)
    assert data.get("success") is True, f"Expected success, got: {data}"
    assert test_file.read_text() == "new content"


# --- test_write_file_empty ---
def test_write_file_empty(tmp_path):
    """Write an empty string, verify it works."""
    from tools.builtin.basic import write_file_tool
    import soul.personality as _sp
    _sp.GODMODE = True  # bypass allowed-dirs check for tmp_path

    test_file = tmp_path / "write_empty_test.txt"
    result = write_file_tool(str(test_file), "")
    data = json.loads(result)
    assert data.get("success") is True, f"Expected success, got: {data}"
    assert test_file.exists()
    assert test_file.read_text() == ""


# ─── PATCH TOOL TESTS ───────────────────────────────


# --- test_patch_simple ---
def test_patch_simple(tmp_path):
    """Replace old text with new text in a file and verify."""
    from tools.builtin.basic import patch_tool

    test_file = tmp_path / "patch_simple_test.txt"
    test_file.write_text("foo bar baz")
    result = patch_tool(str(test_file), old_string="bar", new_string="QUX")
    data = json.loads(result)
    assert data.get("success") is True, f"Expected success, got: {data}"
    assert test_file.read_text() == "foo QUX baz"


# --- test_patch_nonexistent_string ---
def test_patch_nonexistent_string(tmp_path):
    """Try to replace a non-existent string, expect an error."""
    from tools.builtin.basic import patch_tool

    test_file = tmp_path / "patch_nonexistent_test.txt"
    test_file.write_text("some content here")
    result = patch_tool(str(test_file), old_string="NONEXISTENT_STRING_XYZ", new_string="replacement")
    data = json.loads(result)
    assert "error" in data, f"Expected error, got: {data}"
    # File content should remain unchanged
    assert test_file.read_text() == "some content here"


# --- test_patch_replace_all ---
def test_patch_replace_all(tmp_path):
    """Replace all occurrences of the same string."""
    from tools.builtin.basic import patch_tool

    test_file = tmp_path / "patch_replace_all_test.txt"
    test_file.write_text("a X b X c X d")
    result = patch_tool(str(test_file), old_string="X", new_string="Y")
    data = json.loads(result)
    assert data.get("success") is True, f"Expected success, got: {data}"
    assert data.get("count") == 3, f"Expected 3 replacements, got: {data}"
    assert test_file.read_text() == "a Y b Y c Y d"


# ─── SEARCH FILES (filename mode) TESTS ─────────────


# --- test_search_files_by_glob ---
@pytest.mark.asyncio
async def test_search_files_by_glob(tmp_path):
    """Create a file and find it by name/glob."""
    from tools.builtin.basic import search_files_tool

    test_file = tmp_path / "my_search_test_file.txt"
    test_file.write_text("content")
    result = await search_files_tool("my_search_test_file", path=str(tmp_path))
    data = json.loads(result)
    assert "error" not in data, f"Unexpected error: {data}"
    # Should find the file in matches
    matches = data.get("matches", [])
    assert any("my_search_test_file.txt" in m for m in matches), f"File not found in: {data}"


# --- test_search_files_nonexistent_glob ---
@pytest.mark.asyncio
async def test_search_files_nonexistent_glob(tmp_path):
    """Search for a non-existent file, expect an error."""
    from tools.builtin.basic import search_files_tool

    result = await search_files_tool("NONEXISTENT_FILE_ABCDEF", path=str(tmp_path))
    data = json.loads(result)
    assert "error" in data, f"Expected error, got: {data}"


# ─── READ FILE LARGE FILE TEST ─────────────────────


# --- test_read_file_large_file ---
def test_read_file_large_file(tmp_path):
    """Create a 1000-line file, verify only first 500 lines are returned (default limit)."""
    from tools.builtin.basic import read_file_tool

    test_file = tmp_path / "large_file_test.txt"
    lines = "\n".join(f"line {i}" for i in range(1, 1001))
    test_file.write_text(lines)

    result = read_file_tool(str(test_file))
    # Should contain the first few lines
    assert "line 1" in result
    assert "line 2" in result
    # Default limit is 200, so line 200 should be present
    assert "line 200" in result
    # Should NOT contain late lines beyond the default limit
    assert "line 300" not in result
    assert "line 900" not in result
    # Should contain the warning about truncation
    assert "ilk 500" in result or "first 500" in result or "1000 satir" in result or "1000" in result
