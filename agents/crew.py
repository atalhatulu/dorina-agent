"""Multi-agent — planner + researcher + writer + reviewer + fork subagent."""
from __future__ import annotations
import uuid
import json
from datetime import datetime
from core.logger import log


class AgentCrew:
    def __init__(self):
        self.members = []
        self._forks: dict[str, dict] = {}

    def add_member(self, role: str, goal: str):
        self.members.append({"role": role, "goal": goal})
        log.info(f"Added to crew: {role}")

    def add_agent(self, role: str, goal: str):
        """Add a new agent to the crew (alias for add_member())."""
        self.add_member(role, goal)

    def run(self, task: str) -> str:
        log.info(f"Crew started: {task}")
        for m in self.members:
            log.info(f"  [{m['role']}] working...")
        return f"Crew completed: {task}"

    def run_crew(self, task: str) -> str:
        """Multi-agent simulation: each agent returns a status in turn."""
        log.info(f"Crew started: {task}")
        results = []
        for m in self.members:
            result = f"[{m['role']}] working on: {task}"
            log.info(result)
            results.append(result)
        return "\n".join(results)

    def fork_subagent(self, goal: str, tools: list[str] | None = None,
                      bubble_permissions: bool = True) -> str:
        """
        Claude Code-style fork subagent.
        Creates a new subagent with specific tools.
        If bubble_permissions=True, permissions bubble to parent.
        """
        fork_id = uuid.uuid4().hex[:8]
        fork = {
            "id": fork_id,
            "goal": goal,
            "tools": tools or [],
            "bubble_permissions": bubble_permissions,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        self._forks[fork_id] = fork
        # Status: pending → running
        fork["status"] = "running"
        permission_note = " (permissions bubble to parent)" if bubble_permissions else ""
        log.info(f"Fork subagent [{fork_id}]: {goal[:50]}{permission_note}")
        # Simulate
        fork["status"] = "completed"
        fork["result"] = f"Subagent completed: {goal[:80]}"
        return json.dumps({
            "fork_id": fork_id,
            "status": "completed",
            "result": fork["result"],
            "tools_count": len(tools or []),
            "bubble_permissions": bubble_permissions,
        }, ensure_ascii=False)

    def list_forks(self) -> list[dict]:
        """List all fork subagents."""
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

    def get_fork(self, fork_id: str) -> dict | None:
        """Return the status of a specific fork."""
        return self._forks.get(fork_id)


crew = AgentCrew()
