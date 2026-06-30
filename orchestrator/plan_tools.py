"""Planner tool — plan and execute multi-step tasks with dependency graph.

Superpowers: task decomposition + subagent dispatch.
"""

from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="plan_and_execute",
    description="Plan and execute multi-step tasks. Breaks complex requests into atomic sub-tasks, "
                "respects dependencies, and executes independent tasks in parallel. "
                "Use when user asks for multiple things: create+show, research+summarize, compare+save.",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The full user request describing what needs to be done",
            },
            "parallel": {
                "type": "boolean",
                "description": "If True, independent steps execute in parallel (auto-detected if not set)",
                "default": False,
            },
        },
        "required": ["task"],
    },
    toolset="agent",
)
async def plan_and_execute_tool(task: str, parallel: bool = False) -> str:
    """Plan and execute a multi-step task using the Planner engine.

    Flow:
        1. planner.analyze() - decompose into sub-tasks with dependency graph
        2. planner.execute_plan() - run each step respecting dependencies
        3. Independent steps run in parallel via ThreadPoolExecutor
        4. Results collected and returned as structured JSON

    Returns:
        JSON string with execution results, status per step, and summary.
    """
    from orchestrator.planner import planner

    # Analyze and get plan with dependency graph
    plan = planner.analyze(task)

    if parallel:
        plan["parallel"] = True

    # Execute the plan
    result = await planner.execute_plan(plan)
    return result


@register_tool(
    name="plan",
    description="Analyze a request and return a structured plan without executing. "
                "Shows sub-tasks, dependencies, and execution order.",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task or request to analyze",
            },
        },
        "required": ["task"],
    },
    toolset="agent",
)
def plan_tool(task: str) -> str:
    """Analyze a request and return the plan structure (no execution).

    Returns:
        JSON with task graph, steps, layers, and parallel execution info.
    """
    from orchestrator.planner import planner

    plan = planner.analyze(task)

    # Format as readable output
    output = {
        "task": plan["task"],
        "summary": plan["summary"],
        "parallel_possible": plan["parallel"],
        "layers": plan["layers"],
        "steps": [
            {
                "id": s["id"],
                "description": s["description"],
                "tool": s["tool"],
                "depends_on": s["depends_on"],
            }
            for s in plan["steps"]
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)
