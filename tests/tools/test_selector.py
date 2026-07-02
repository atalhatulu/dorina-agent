"""Toolset tests — aktif toolset sistemi."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestToolsetManager:
    def test_default_toolsets(self):
        """Default toolsets should include core categories."""
        from tools.toolset import DEFAULT_TOOLSETS
        assert "file" in DEFAULT_TOOLSETS
        assert "web" in DEFAULT_TOOLSETS
        assert "terminal" in DEFAULT_TOOLSETS

    def test_toolset_labels_exist(self):
        """All categories should have labels."""
        from tools.toolset import TOOLSET_LABELS
        assert "file" in TOOLSET_LABELS
        assert "web" in TOOLSET_LABELS
        assert "terminal" in TOOLSET_LABELS
        assert "delegation" in TOOLSET_LABELS
        assert "system" in TOOLSET_LABELS
        assert "mcp" in TOOLSET_LABELS
        assert len(TOOLSET_LABELS) >= 6

    def test_tools_enable_valid_toolset(self):
        """tools_enable with valid toolset should succeed."""
        from tools.toolset import tools_enable, ACTIVE_TOOLSETS, DEFAULT_TOOLSETS
        # Reset
        ACTIVE_TOOLSETS.clear()
        ACTIVE_TOOLSETS.update(DEFAULT_TOOLSETS)
        
        result = tools_enable("mcp")
        assert "✅" in result
        assert "mcp" in ACTIVE_TOOLSETS

    def test_tools_enable_invalid_toolset(self):
        """tools_enable with invalid toolset should return error."""
        from tools.toolset import tools_enable
        result = tools_enable("nonexistent")
        assert "❌" in result

    def test_tools_enable_already_active(self):
        """Enabling an already active toolset should inform."""
        from tools.toolset import tools_enable, ACTIVE_TOOLSETS, DEFAULT_TOOLSETS
        ACTIVE_TOOLSETS.clear()
        ACTIVE_TOOLSETS.update(DEFAULT_TOOLSETS)
        
        result = tools_enable("file")
        assert "ℹ️" in result

    def test_get_active_schemas(self):
        """get_active_schemas should return schemas for active toolsets."""
        from tools.toolset import get_active_schemas, ACTIVE_TOOLSETS, DEFAULT_TOOLSETS
        # Load tools first
        import tools.builtin.basic
        ACTIVE_TOOLSETS.clear()
        ACTIVE_TOOLSETS.update(DEFAULT_TOOLSETS)
        
        schemas = get_active_schemas()
        assert len(schemas) >= 3
        names = {s["function"]["name"] for s in schemas}
        assert "read_file" in names or "terminal" in names

    def test_toolset_summary(self):
        """toolset_summary should return formatted string."""
        from tools.toolset import toolset_summary
        summary = toolset_summary()
        assert "KULLANILABILIR" in summary
        assert "FILE" in summary
        assert "tools_enable" in summary
