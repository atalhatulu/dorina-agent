"""
GoalManager — Persistant background goal yonetimi.

Her goal bir SubAgent olarak arka planda calisir:
  1. Planning: ne yapacagini belirler
  2. Execution: adimlari uygular
  3. Verification: sonucu kontrol eder
  4. Fix (opsiyonel): hata varsa duzeltir
  5. Notification: bitince kullaniciya bildirir

Kullanici /goals ile goal'leri gorur, /goal cancel <id> ile iptal eder.
LLM delegate_goal tool'u ile kendi goal'ini baslatir.
"""

from __future__ import annotations
import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional
from core.logger import log
from core.event_bus import bus


@dataclass
class Goal:
    """Tek bir goal'in durumu."""
    id: str
    name: str
    description: str
    status: str = "pending"      # pending → running → completed/failed/cancelled
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    result: str = ""
    error: str = ""
    turn_count: int = 0
    _bg_task_id: str = ""

    @property
    def elapsed(self) -> str:
        end = self.completed_at or time.time()
        s = end - self.created_at
        if s < 60:
            return f"{s:.0f}s"
        elif s < 3600:
            return f"{s // 60:.0f}m {s % 60:.0f}s"
        return f"{s // 3600:.0f}h {(s % 3600) // 60:.0f}m"

    @property
    def short_id(self) -> str:
        return self.id[:8]


class GoalManager:
    """Goal'leri yonetir, background'da calistirir, bitince bildirir."""

    def __init__(self):
        self._goals: dict[str, Goal] = {}
        log.info("GoalManager baslatildi")

    def create_goal(self, name: str, description: str = "") -> str:
        """Yeni goal olustur, ID'sini dondur."""
        goal_id = uuid.uuid4().hex[:12]
        goal = Goal(id=goal_id, name=name, description=description)
        self._goals[goal_id] = goal
        log.info("Goal olusturuldu: [%s] %s", goal.short_id, name)
        bus.publish("goal:created", goal_id=goal_id, name=name)
        return goal_id

    async def start_goal(self, goal_id: str, toolsets: list[str] = None) -> str:
        """Goal'i SubAgent olarak background'da baslat."""
        from tools.delegate import SubAgent
        from bg_tools.task_manager import task_manager

        goal = self._goals.get(goal_id)
        if not goal:
            return json_error(f"Goal bulunamadi: {goal_id}")
        if goal.status != "pending":
            return json_error(f"Goal zaten {goal.status} durumunda")

        goal.status = "running"
        bus.publish("goal:started", goal_id=goal_id, name=goal.name)

        # Background task olarak sub-agent baslat
        async def _run_goal():
            agent = SubAgent(
                goal=goal.description or goal.name,
                context=f"Goal adi: {goal.name}",
                toolsets=toolsets or ["file", "web", "terminal"],
            )
            result = await agent.run()
            goal.turn_count = agent.turn_count
            if agent.status == "completed":
                goal.status = "completed"
                goal.result = result[:500] if result else ""
                goal.completed_at = time.time()
                bus.publish("goal:completed", goal_id=goal_id, name=goal.name)
                log.info("Goal tamamlandi: [%s] %s (%s)", goal.short_id, goal.name, goal.elapsed)
                preview = (goal.result[:100].replace("\n", " ") if goal.result else "")
                return f"[{goal.name}] tamamlandi ({goal.elapsed})\n  {preview}"
            else:
                goal.status = "failed"
                goal.error = agent.error or "bilinmeyen hata"
                goal.completed_at = time.time()
                bus.publish("goal:failed", goal_id=goal_id, name=goal.name, error=goal.error)
                log.error("Goal basarisiz: [%s] %s: %s", goal.short_id, goal.name, goal.error)
                return f"[{goal.name}] basarisiz: {goal.error}"

        bg_id = task_manager.start(_run_goal(), name=f"goal:{goal.short_id}")
        goal._bg_task_id = bg_id

        return json.dumps({
            "goal_id": goal_id,
            "name": goal.name,
            "status": "running",
            "message": f"Goal baslatildi: {goal.name}",
        }, ensure_ascii=False)

    def list_goals(self, status_filter: str = "") -> list[dict]:
        """Tum goal'leri listele."""
        goals = self._goals.values()
        if status_filter:
            goals = [g for g in goals if g.status == status_filter]
        return [
            {
                "id": g.short_id,
                "name": g.name,
                "status": g.status,
                "elapsed": g.elapsed,
                "created_at": time.strftime("%H:%M", time.localtime(g.created_at)),
            }
            for g in sorted(goals, key=lambda x: x.created_at, reverse=True)
        ]

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Goal detayini getir."""
        full_id = self._resolve_id(goal_id)
        if full_id:
            return self._goals.get(full_id)
        return None

    def cancel_goal(self, goal_id: str) -> bool:
        """Goal'i iptal et."""
        goal = self.get_goal(goal_id)
        if not goal:
            return False
        if goal.status not in ("pending", "running"):
            return False
        goal.status = "cancelled"
        goal.completed_at = time.time()
        goal.result = "iptal edildi"
        bus.publish("goal:cancelled", goal_id=goal.id, name=goal.name)
        log.info("Goal iptal edildi: [%s] %s", goal.short_id, goal.name)
        return True

    def running_count(self) -> int:
        """Aktif goal sayisi."""
        return sum(1 for g in self._goals.values() if g.status == "running")

    def _resolve_id(self, short_or_full: str) -> Optional[str]:
        """Kisa ID'den tam ID'yi bul."""
        for full_id in self._goals:
            if full_id.startswith(short_or_full):
                return full_id
        return None


def json_error(msg: str) -> str:
    return json.dumps({"error": msg}, ensure_ascii=False)


# Module-level singleton
goal_manager = GoalManager()
