"""
Task System — Claude Code'dan esinlenilmiş görev yönetimi.

Task tipleri:
- local_bash: Shell komutu çalıştır
- local_agent: Alt-agent çağır
- local_workflow: Çok adımlı iş akışı
- monitor: Arka planda izle

Status: pending → running → completed/failed/killed
"""

from __future__ import annotations
import uuid
import time
import threading
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass, field
from core.logger import log


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class TaskType(Enum):
    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR = "monitor"


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: TaskType = TaskType.LOCAL_BASH
    status: TaskStatus = TaskStatus.PENDING
    goal: str = ""
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    parent_id: Optional[str] = None  # üst task varsa


class TaskRunner:
    """Task'ları yönet ve çalıştır."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._max_tasks = 50

    def create(self, type: str, goal: str, parent_id: str = "") -> Task:
        """Yeni task oluştur."""
        task = Task(
            type=TaskType(type),
            goal=goal,
            parent_id=parent_id or None,
        )
        with self._lock:
            self.tasks[task.id] = task
            # Clean old tasks
            while len(self.tasks) > self._max_tasks:
                oldest = min(self.tasks.keys(), key=lambda k: self.tasks[k].created_at)
                del self.tasks[oldest]
        return task

    def start(self, task_id: str) -> bool:
        """Task'ı başlat."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return False
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
        return True

    def complete(self, task_id: str, result: str = ""):
        """Task'ı tamamlandı olarak işaretle."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.finished_at = time.time()

    def fail(self, task_id: str, error: str = ""):
        """Task'ı hatalı işaretle."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.FAILED
            task.error = error
            task.finished_at = time.time()

    def kill(self, task_id: str):
        """Task'ı iptal et."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.KILLED
            task.finished_at = time.time()

    def get(self, task_id: str) -> Optional[Task]:
        """Task detayı."""
        return self.tasks.get(task_id)

    def list(self, status: str = "", limit: int = 20) -> list[dict]:
        """Task'ları listele."""
        with self._lock:
            tasks = list(self.tasks.values())
            if status:
                tasks = [t for t in tasks if t.status.value == status]
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return [
                {
                    "id": t.id,
                    "type": t.type.value,
                    "status": t.status.value,
                    "goal": t.goal[:50],
                    "duration": round(t.finished_at - t.started_at, 1) if t.finished_at and t.started_at else None,
                    "parent": t.parent_id,
                }
                for t in tasks[:limit]
            ]

    def run_bash(self, command: str, timeout: int = 30) -> Task:
        """Shell komutu çalıştır (local_bash)."""
        import subprocess
        task = self.create("local_bash", command)
        self.start(task.id)
        try:
            result = subprocess.run(command, shell=True, capture_output=True,
                                   text=True, timeout=timeout)
            output = result.stdout[-2000:] if result.stdout else ""
            if result.stderr:
                output += f"\nSTDERR: {result.stderr[-500:]}"
            self.complete(task.id, output or f"Exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            self.fail(task.id, f"Timeout ({timeout}s)")
        except Exception as e:
            self.fail(task.id, str(e))
        return task

    def stats(self) -> dict:
        """Task istatistikleri."""
        with self._lock:
            total = len(self.tasks)
            by_status = {}
            for t in self.tasks.values():
                s = t.status.value
                by_status[s] = by_status.get(s, 0) + 1
            return {
                "total": total,
                "by_status": by_status,
                "active": sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING),
            }


# Global instance
tasks = TaskRunner()
