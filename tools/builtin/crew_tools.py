"""Crew run tool — executes a real multi-agent crew via SubAgent delegation.

Exposes the (previously unused) agents.crew module to the agent. A crew is a
set of named roles (planner, researcher, writer, reviewer...) run as isolated
SubAgents, each with its own think→act loop and tool lanes. Supports
sequential and parallel execution, plus single fork sub-agents.
"""
from __future__ import annotations

import json

from tools.registry import register_tool
from agents.crew import crew, AgentCrew


def _role_fmt(roles: list[str]) -> str:
    return ", ".join(roles) if roles else "planner, researcher, writer, reviewer"


@register_tool(
    name="crew_run",
    description=(
        "Run a multi-agent crew: spawn several role-focused SubAgents (e.g. "
        "planner, researcher, writer, reviewer) to work on one shared task, "
        "each with its own isolated think→act loop and tools. Use for "
        "multi-perspective work like research-then-write or review pipelines. "
        "Returns per-member results. For a parallel dispatch that returns "
        "immediately (background), use delegate_goal instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The shared task given to every crew member.",
            },
            "roles": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Crew roles to spawn. Supported lanes: planner, researcher, "
                    "writer, reviewer, or custom role labels. Default: planner, "
                    "researcher, writer, reviewer."
                ),
            },
            "parallel": {
                "type": "boolean",
                "description": "Run members in parallel (True) or sequentially (False). Default True.",
            },
        },
        "required": ["task"],
    },
    toolset="delegation",
)
def crew_run_tool(task: str, roles: list[str] | None = None, parallel: bool = True) -> str:
    """Run a crew of SubAgents on a shared task and return aggregated JSON."""
    import asyncio
    try:
        crew_inst = AgentCrew()
        role_list = roles or ["planner", "researcher", "writer", "reviewer"]
        for r in role_list:
            crew_inst.add_agent(r, "")
        if parallel:
            return asyncio.run(crew_inst.run_crew_parallel(task))
        return asyncio.run(crew_inst.run_crew(task))
    except (ImportError, AttributeError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="crew_fork",
    description=(
        "Run a single isolated sub-agent (fork) for a focused goal. This is the "
        "real SubAgent backend, not a simulation: the fork executes its own "
        "think→act loop with its own toolset and returns its actual result. "
        "Use for self-contained subtasks (summarize, analyze, draft) while the "
        "main agent keeps working."
    ),
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The focused goal for the fork sub-agent.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Toolsets for the fork (file, web, terminal, git, memory, research). Default: file, web, terminal.",
            },
            "context": {
                "type": "string",
                "description": "Optional context passed to the fork (paths, prior results).",
            },
        },
        "required": ["goal"],
    },
    toolset="delegation",
)
def crew_fork_tool(goal: str, tools: list[str] | None = None, context: str = "") -> str:
    """Run a real fork sub-agent and return its JSON result."""
    import asyncio
    try:
        return asyncio.run(crew.fork_subagent(goal=goal, tools=tools, context=context))
    except (ImportError, AttributeError, OSError) as e:
        return json.dumps({"error": str(e)})