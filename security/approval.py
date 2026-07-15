"""Command approval system — for destructive or sensitive operations.

always_allow:   Tools in this list pass through without approval.
ask_always:     Tools in this list always require approval.
Other tools:   Evaluated by mode (smart/manual/off).
"""

from __future__ import annotations
from tools.security import is_destructive
from core.config import settings
from core.constants import t


class Approval:
    """Approval mechanism for destructive or sensitive operations."""

    MODE_SMART = "smart"
    MODE_MANUAL = "manual"
    MODE_OFF = "off"

    def __init__(self, mode: str | None = None):
        self.mode = mode or settings.tools.approval_mode
        # Read approval lists from config
        self.always_allow: list[str] = list(settings.security.always_allow or [])
        self.ask_always: list[str] = list(settings.security.ask_always or [])

    def needs_approval(self, tool_name: str, arguments: dict) -> bool:
        """Does this operation require approval?"""
        from core.mode_manager import modes
        if modes.is_on("godmode") or modes.is_on("auto"):
            return False

        if self.mode == self.MODE_OFF:
            return False

        # always_allow: skip directly, no approval required
        if tool_name in self.always_allow:
            return False

        # ask_always: always ask for approval
        if tool_name in self.ask_always:
            return True

        # Terminal commands
        if tool_name == "terminal":
            command = arguments.get("command", "")
            if is_destructive(command):
                return True

        # File deletion
        if tool_name in ("delete_file", "rm"):
            return True

        # Smart mode: fewer approvals
        if self.mode == self.MODE_SMART:
            return False  # Only the most risky operations require approval

        return True

    def approve(self, tool_name: str, arguments: dict) -> bool:
        """Ask the user for approval."""
        if not self.needs_approval(tool_name, arguments):
            return True

        print(t("approval_tool_called", tool=tool_name, arguments=arguments))
        resp = input(t("approval_prompt_confirm")).strip().lower()
        return resp in ("", "e", "evet", "y", "yes")

    def reload_from_config(self):
        """Reload config file (hot-reload)."""
        from core.config import Settings
        fresh = Settings.load()
        self.mode = fresh.tools.approval_mode
        self.always_allow = list(fresh.security.always_allow or [])
        self.ask_always = list(fresh.security.ask_always or [])


approval = Approval()


def _approval_hook(tool_name: str, arguments: dict) -> bool:
    """Pre-execution hook: get approval before tool is called."""
    return approval.approve(tool_name, arguments)


# Register itself with the pipeline (lazy import)
def _register_approval_hook():
    try:
        from hooks.lifecycle import pipeline
        pipeline.register("pre_execution", _approval_hook)
    except ImportError:
        pass  # Silently skip if pipeline isn't ready yet


_register_approval_hook()
