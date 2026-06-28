"""Tests for security/approval.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestApproval:
    def test_off_mode_never_approves(self, fresh_approval):
        appr = fresh_approval  # mode="off"
        assert appr.needs_approval("delete_file", {}) is False
        assert appr.needs_approval("terminal", {"command": "rm -rf /"}) is False

    def test_smart_mode_always_allow(self):
        from security.approval import Approval
        appr = Approval(mode="smart")
        # always_allow tools should not need approval
        assert appr.needs_approval("read_file", {"path": "/etc/passwd"}) is False
        assert appr.needs_approval("search_files", {"pattern": "test"}) is False

    def test_smart_mode_ask_always(self):
        from security.approval import Approval
        appr = Approval(mode="smart")
        # ask_always tools should need approval
        assert appr.needs_approval("delete_file", {}) is True
        assert appr.needs_approval("execute_code", {}) is True

    def test_destructive_terminal_command(self):
        from security.approval import Approval
        appr = Approval(mode="smart")
        assert appr.needs_approval("terminal", {"command": "rm -rf /home"}) is True
        assert appr.needs_approval("terminal", {"command": "ls -la"}) is False

    def test_manual_mode_not_always_allow_nonlisted(self):
        from security.approval import Approval
        appr = Approval(mode="manual")
        # Tools not in always_allow should need approval
        assert appr.needs_approval("execute_code", {"code": "test"}) is True
        assert appr.needs_approval("bulk_execute_command", {}) is True

    def test_manual_mode_always_allow(self):
        from security.approval import Approval
        appr = Approval(mode="manual")
        assert appr.needs_approval("web_search", {}) is False  # in always_allow
        # 'get_weather' is in always_allow
        assert appr.needs_approval("get_weather", {"location": "Istanbul"}) is False

    def test_delete_file_triggers_approval(self):
        from security.approval import Approval
        appr = Approval(mode="smart")
        assert appr.needs_approval("delete_file", {"path": "/tmp/x"}) is True
        assert appr.needs_approval("rm", {"path": "/tmp/x"}) is True

    def test_approve_returns_true_when_not_needed(self, fresh_approval):
        appr = fresh_approval  # mode="off"
        assert appr.approve("delete_file", {}) is True

    def test_reload_from_config(self, fresh_approval):
        appr = fresh_approval
        # Should not crash
        appr.reload_from_config()
        assert appr.mode is not None
