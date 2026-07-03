"""
Goal tools: delegate_goal — persistent background goal management for LLM.

The LLM can set its own goals and run them in the background using this tool.
The user tracks progress with /goals and cancels with /goal cancel.
"""

from __future__ import annotations

from tools.registry import register_tool
from orchestrator.goal_manager import goal_manager


@register_tool(
    name="delegate_goal",
    description=(
        "Run a goal in the background. "
        "Returns immediately, goal runs in background. "
        "Notification sent on completion. "
        "Use /goals to check status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short goal name (e.g., 'run tests')",
            },
            "description": {
                "type": "string",
                "description": (
                    "Detailed goal description. The SubAgent's task. "
                    "Must be clear and specific."
                ),
            },
            "toolsets": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "file", "web", "terminal",
                        "git", "memory", "research",
                    ],
                },
                "description": "Tool categories the goal can use",
                "default": ["file", "web", "terminal"],
            },
        },
        "required": ["name", "description"],
    },
    toolset="delegation",
)
async def delegate_goal_tool(
    name: str,
    description: str,
    toolsets: list[str] = None,
) -> str:
    """Start background goal, return immediately."""
    import json
    if toolsets is None:
        toolsets = ["file", "web", "terminal"]

    goal_id = goal_manager.create_goal(name=name, description=description)
    result = await goal_manager.start_goal(goal_id, toolsets=toolsets)
    return result
