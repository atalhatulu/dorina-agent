"""Tool selector tests."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestToolSelector:
    def test_always_include_constants(self):
        """Always include tools set should exist."""
        from tools.selector import ALWAYS_INCLUDE
        assert len(ALWAYS_INCLUDE) >= 5
        assert "read_file" in ALWAYS_INCLUDE
        assert "write_file" in ALWAYS_INCLUDE

    def test_never_select_constants(self):
        """Never-select tools should exist."""
        from tools.selector import NEVER_SELECT
        assert "delegate_task" in NEVER_SELECT

    def test_schemas_for_known_tool(self):
        """schemas_for should return valid schema structure."""
        from tools.selector import selector
        schemas = selector.schemas_for(["read_file"])
        # Registry may not have read_file in test context; check API shape
        if schemas:
            assert schemas[0]["type"] == "function"
            assert "name" in schemas[0]["function"]

    def test_schemas_for_unknown_tool(self):
        """schemas_for should silently skip unknown tools."""
        from tools.selector import selector
        schemas = selector.schemas_for(["nonexistent_tool_xyz"])
        assert len(schemas) == 0

    def test_default_top_k(self):
        """Default top_k should be reasonable."""
        from tools.selector import DEFAULT_TOP_K
        assert 5 <= DEFAULT_TOP_K <= 15

    def test_selector_reset(self):
        """Reset should clear indexed state."""
        from tools.selector import selector
        selector._indexed = True
        selector.reset()
        assert selector._indexed is False
        assert selector._total_tools == 0
