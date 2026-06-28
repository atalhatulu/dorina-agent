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
        log.info(f"Crew'e eklendi: {role}")

    def add_agent(self, role: str, goal: str):
        """Crew'e yeni agent ekle (add_member() alias'ı)."""
        self.add_member(role, goal)

    def run(self, task: str) -> str:
        log.info(f"Crew basladi: {task}")
        for m in self.members:
            log.info(f"  [{m['role']}] calisiyor...")
        return f"Crew tamamladi: {task}"

    def run_crew(self, task: str) -> str:
        """Multi-agent simülasyonu: her agent sırayla 'görev yapıyorum' döner."""
        log.info(f"Crew basladi: {task}")
        results = []
        for m in self.members:
            result = f"[{m['role']}] görev yapıyorum: {task}"
            log.info(result)
            results.append(result)
        return "\n".join(results)

    def fork_subagent(self, goal: str, tools: list[str] | None = None,
                      bubble_permissions: bool = True) -> str:
        """
        Claude Code tarzı fork subagent.
        Yeni bir subagent oluştur, belirli tool'larla çalıştır.
        bubble_permissions=True ise izinleri parent'a bildirir.
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
        permission_note = " (izinler parent'a bildirilir)" if bubble_permissions else ""
        log.info(f"Fork subagent [{fork_id}]: {goal[:50]}{permission_note}")
        # Simule et
        fork["status"] = "completed"
        fork["result"] = f"Subagent tamamladi: {goal[:80]}"
        return json.dumps({
            "fork_id": fork_id,
            "status": "completed",
            "result": fork["result"],
            "tools_count": len(tools or []),
            "bubble_permissions": bubble_permissions,
        }, ensure_ascii=False)

    def list_forks(self) -> list[dict]:
        """Tüm fork subagent'ları listele."""
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
        """Belirli bir fork'un durumunu döndür."""
        return self._forks.get(fork_id)


crew = AgentCrew()
