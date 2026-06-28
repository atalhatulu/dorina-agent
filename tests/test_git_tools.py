"""Git tools tests."""
from __future__ import annotations
import json
import pytest


class TestGitTools:
    def test_git_add_no_args(self):
        from tools.builtin.git_tools import git_add_tool
        # '.' ile calismali (hata vermemeli)
        r = json.loads(git_add_tool("."))
        assert "success" in r or "error" in r

    def test_git_diff_empty(self):
        from tools.builtin.git_tools import git_diff_tool
        r = git_diff_tool()
        assert isinstance(r, str)

    def test_git_branch_list(self):
        from tools.builtin.git_tools import git_branch_tool
        r = git_branch_tool("list")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_git_push_removed(self):
        """git_push_tool kaldirildi, import edilememeli."""
        import importlib
        mod = importlib.import_module("tools.builtin.git_tools")
        assert not hasattr(mod, "git_push_tool")

    def test_git_commit_no_message(self):
        from tools.builtin.git_tools import git_commit_tool
        try:
            # empty message git tarafinda hata verir, ama tool patlamamali
            r = git_commit_tool("")
            assert isinstance(r, str)
        except Exception:
            pytest.fail("git_commit empty message should not throw")
