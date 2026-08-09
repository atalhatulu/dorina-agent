"""Multi-agent crew — real SubAgent delegation behind the scenes.

Previously this file simulated a "planner + researcher + writer + reviewer"
crew by merely logging status strings (a facade). Every execution path now
uses the real `SubAgent` from `tools.delegate`, so each crew member runs an
isolated mini-loop with its own tools and returns an actual result.

Usage (async):
    from agents.crew import crew
    crew.add_agent("researcher", "Research X")
    result = await crew.run_crew("Build a plan for Y")
    fork = await crew.fork_subagent("Summarize Z", tools=["file", "web"])
"""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from typing import Optional

from core.logger import log
from tools.delegate import SubAgent, DelegateManager


class AgentCrew:
    """A crew of named roles, each run as a real SubAgent.

    Roles are collected via add_member/add_agent, then executed either
    sequentially (`run_crew`) or in parallel (`run_crew_parallel`). Each
    role gets the shared task as its goal, with the role labelled so its
    focus is explicit.
    """

    # Default toolset per crew role — keeps research/writing lanes lean.
    ROLE_TOOLSETS: dict[str, list[str]] = {
        "planner": ["file", "web", "terminal"],
        "researcher": ["file", "web"],
        "writer": ["file", "terminal"],
        "reviewer": ["file", "terminal"],
    }

    def __init__(self):
        self.members: list[dict] = []
        self._forks: dict[str, dict] = {}
        self._delegate = DelegateManager()

    # ── Member management ────────────────────────────────────────────

    def add_member(self, role: str, goal: str):
        """Add a crew member by role (advisory label) and its focused goal."""
        if not role or not goal:
            return
        self.members.append({"role": role, "goal": goal})
        log.info(f"Added to crew: {role} → {goal[:60]}")

    def add_agent(self, role: str, goal: str):
        """Alias for add_member()."""
        self.add_member(role, goal)

    def clear(self):
        """Remove all members and fork records."""
        self.members.clear()
        self._forks.clear()

    def member_count(self) -> int:
        return len(self.members)

    def _toolsets_for(self, role: str) -> list[str]:
        """Resolve role → toolsets, falling back to a sensible default."""
        normalized = role.strip().lower()
        for key, value in self.ROLE_TOOLSETS.items():
            if key in normalized or normalized in key:
                return value
        return ["file", "web", "terminal"]

    def _role_goal(self, member: dict, task: str) -> str:
        """Build the SubAgent goal for one member given the shared task."""
        role = member.get("role", "worker")
        focused = member.get("goal", "").strip()
        base = (
            f"As the '{role}' of a crew, complete this task: {task}"
            if focused
            else f"As the '{role}' of a crew, complete this task: {task}. Focus: {focused}"
        )
        return base

    # ── Real execution ───────────────────────────────────────────────

    async def run_member(self, member: dict, task: str) -> dict:
        """Run a single crew member as a real SubAgent. Returns result dict."""
        role = member.get("role", "worker")
        agent = SubAgent(
            goal=self._role_goal(member, task),
            context=f"Crew role: {role}",
            toolsets=self._toolsets_for(role),
        )
        log.info(f"[crew:{role}] launching SubAgent ({agent.id})")
        result = await agent.run()
        return {
            "role": role,
            "status": agent.status,
            "result": (result or ""),
            "error": agent.error or "",
            "turns": agent.turn_count,
        }

    async def run_crew(self, task: str) -> str:
        """Run all members sequentially, aggregating their results."""
        if not self.members:
            return json.dumps(
                {"status": "empty", "message": "No crew members. Use add_agent()."},
                ensure_ascii=False,
            )
        log.info(f"Crew started ({len(self.members)} members): {task}")
        results = []
        for member in self.members:
            results.append(await self.run_member(member, task))
        return _summary_payload("completed", results)

    async def run_crew_parallel(self, task: str) -> str:
        """Run all members in parallel as independent SubAgents."""
        if not self.members:
            return json.dumps(
                {"status": "empty", "message": "No crew members. Use add_agent()."},
                ensure_ascii=False,
            )
        log.info(f"Crew (parallel) started ({len(self.members)} members): {task}")
        results = await asyncio.gather(
            *[self.run_member(m, task) for m in self.members],
            return_exceptions=True,
        )
        cleaned = []
        for r in results:
            if isinstance(r, Exception):
                cleaned.append({"status": "error", "error": str(r)})
            else:
                cleaned.append(r)
        return _summary_payload("completed", cleaned)

    # ── Real fork subagent ───────────────────────────────────────────

    async def fork_subagent(
        self,
        goal: str,
        tools: Optional[list[str]] = None,
        bubble_permissions: bool = True,
        context: str = "",
    ) -> str:
        """Create and run a real, isolated sub-agent for a focused goal.

        Unlike the old implementation this is not a simulation: a genuine
        SubAgent executes the goal with its own loop and tools, and the
        returned payload carries the actual result/status.
        """
        fork_id = uuid.uuid4().hex[:8]
        toolsets = tools or ["file", "web", "terminal"]
        agent = SubAgent(
            goal=goal,
            context=(context or "Fork sub-agent"),
            toolsets=toolsets,
        )
        fork = {
            "id": fork_id,
            "goal": goal,
            "tools": toolsets,
            "bubble_permissions": bubble_permissions,
            "status": "running",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "subagent_id": agent.id,
        }
        self._forks[fork_id] = fork

        log.info(f"Fork subagent [{fork_id}] ({agent.id}): {goal[:60]}")
        try:
            result = await agent.run()
            fork.update(
                {"status": agent.status, "result": result or "", "turns": agent.turn_count}
            )
        except Exception as e:  # noqa: BLE001 — stabilize the record for the caller
            fork.update({"status": "error", "error": str(e)})
            result = f'{{"error": "{e}"}}'

        return json.dumps(
            {
                "fork_id": fork_id,
                "status": fork["status"],
                "result": fork.get("result", ""),
                "error": fork.get("error", ""),
                "tools_count": len(toolsets),
                "bubble_permissions": bubble_permissions,
            },
            ensure_ascii=False,
        )

    def list_forks(self) -> list[dict]:
        return [
            {
                "id": f["id"],
                "goal": f["goal"][:60],
                "status": f["status"],
                "tools": len(f.get("tools", [])),
                "created": f["created_at"],
            }
            for f in self._forks.values()
        ]

    def get_fork(self, fork_id: str) -> Optional[dict]:
        return self._forks.get(fork_id)

    @property
    def active_forks(self) -> list[dict]:
        return [f for f in self._forks.values() if f.get("status") in ("running", "pending")]


def _summary_payload(status: str, results: list[dict]) -> str:
    """Aggregate per-member results into a single JSON summary."""
    return json.dumps(
        {
            "status": status,
            "members": [
                {
                    "role": r.get("role"),
                    "status": r.get("status"),
                    "error": r.get("error", ""),
                    "turns": r.get("turns", 0),
                    "result": (r.get("result") or "")[:500],
                }
                for r in results
            ],
        },
        ensure_ascii=False,
    )


# Module-level singleton
crew = AgentCrew()