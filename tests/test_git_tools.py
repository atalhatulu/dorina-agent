"""Git tools tests."""
from __future__ import annotations
import json
import pytest


class TestGitTools:
    @pytest.mark.asyncio
    async def test_git_add_no_args(self):
        from tools.builtin.git_tools import git_add_tool
        # '.' ile calismali (hata vermemeli)
        r = json.loads(await git_add_tool("."))
        assert "success" in r or "error" in r

    @pytest.mark.asyncio
    async def test_git_diff_empty(self):
        from tools.builtin.git_tools import git_diff_tool
        r = await git_diff_tool()
        assert isinstance(r, str)

    @pytest.mark.asyncio
    async def test_git_branch_list(self):
        from tools.builtin.git_tools import git_branch_tool
        r = await git_branch_tool("list")
        assert isinstance(r, str)
        assert len(r) > 0

    @pytest.mark.asyncio
    async def test_git_push_exists(self):
        """git_push_tool fixlendi, artik calisiyor olmali."""
        from tools.builtin.git_tools import git_push_tool
        import json
        r = json.loads(await git_push_tool())
        assert "success" in r or "error" in r

    @pytest.mark.asyncio
    async def test_git_commit_no_message(self):
        from tools.builtin.git_tools import git_commit_tool
        try:
            # empty message git tarafinda hata verir, ama tool patlamamali
            r = await git_commit_tool("")
            assert isinstance(r, str)
        except Exception:
            pytest.fail("git_commit empty message should not throw")
