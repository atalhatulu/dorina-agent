"""Lifecycle hooks — pre/post tool events and hook pipeline.

Pattern: Claude Code Hook Lifecycle + Event Bus Pub/Sub
Each hook is a pipeline stage: validation → transform → execute → post-process
"""
from __future__ import annotations
from typing import Callable, Any
from core.logger import log


class HookPipeline:
    """Pre/Post hook pipeline.

    Stages:
      1. pre_execution  → validation before tool call (return False to cancel)
      2. param_transform → can modify parameters (returns dict)
      3. post_processing → after result (can modify result string)
    """

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {
            "pre_execution": [],
            "param_transform": [],
            "post_processing": [],
        }

    def register(self, stage: str, callback: Callable):
        """Register a hook. stage: pre_execution | param_transform | post_processing"""
        if stage in self._hooks:
            self._hooks[stage].append(callback)
            log.debug(f"Hook registered: stage={stage}, callback={callback.__name__}")
        else:
            log.warning(f"Unknown hook stage: {stage}")

    def unregister(self, stage: str, callback: Callable):
        """Unregister a hook."""
        if stage in self._hooks:
            self._hooks[stage] = [cb for cb in self._hooks[stage] if cb is not callback]

    def unregister_all(self, stage: str | None = None):
        """Clear all hooks in a specific stage, or all stages."""
        if stage:
            self._hooks[stage] = []
        else:
            for s in self._hooks:
                self._hooks[s] = []

    def run_pre_execution(self, tool_name: str, arguments: dict) -> bool:
        """Pre-execution validation. Returns False to cancel the tool."""
        for cb in self._hooks["pre_execution"]:
            try:
                result = cb(tool_name=tool_name, arguments=arguments)
                if result is False:
                    log.info(f"Pre-execution hook cancelled: tool={tool_name}, hook={cb.__name__}")
                    return False
            except Exception as e:
                log.warning(f"Pre-execution hook error [{cb.__name__}]: {e}")
        return True

    def run_param_transform(self, tool_name: str, arguments: dict) -> dict:
        """Parameter transform chain. Each hook returns a dict."""
        current = dict(arguments)
        for cb in self._hooks["param_transform"]:
            try:
                result = cb(tool_name=tool_name, arguments=current)
                if isinstance(result, dict):
                    current = result
            except Exception as e:
                log.warning(f"Param transform hook error [{cb.__name__}]: {e}")
        return current

    def run_post_processing(self, tool_name: str, arguments: dict, result: str) -> str:
        """Post-processing chain. Each hook returns a result string."""
        current = result
        for cb in self._hooks["post_processing"]:
            try:
                new_result = cb(tool_name=tool_name, arguments=arguments, result=current)
                if isinstance(new_result, str):
                    current = new_result
            except Exception as e:
                log.warning(f"Post-processing hook error [{cb.__name__}]: {e}")
        return current

    def stage_count(self, stage: str | None = None) -> int:
        """Return hook count."""
        if stage:
            return len(self._hooks.get(stage, []))
        return sum(len(v) for v in self._hooks.values())

    def list_hooks(self) -> dict[str, list[str]]:
        """List all hooks by name."""
        return {
            stage: [cb.__name__ for cb in cbs]
            for stage, cbs in self._hooks.items()
        }


# Global hook pipeline
pipeline = HookPipeline()
