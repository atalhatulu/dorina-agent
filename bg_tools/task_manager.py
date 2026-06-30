import asyncio
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Coroutine
from core.logger import log

@dataclass
class BackgroundTask:
    id: str
    name: str
    status: str = "running"  # running, done, failed, cancelled
    result: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    _asyncio_task: Optional[asyncio.Task] = None
    _process: Optional[asyncio.subprocess.Process] = None

    @property
    def elapsed(self) -> str:
        end = self.finished_at or time.time()
        s = end - self.started_at
        return f"{s:.0f}s" if s < 60 else f"{s//60:.0f}m {s%60:.0f}s"

class TaskManager:
    def __init__(self):
        self._tasks: dict[str, BackgroundTask] = {}
        self._pending_notifications: list[str] = []

    def start(self, coro: Coroutine, name: str, process: Optional[asyncio.subprocess.Process] = None) -> str:
        """Start a coroutine in the background and return its task ID."""
        task_id = uuid.uuid4().hex[:8]
        task = BackgroundTask(id=task_id, name=name, _process=process)
        self._tasks[task_id] = task

        async def _run():
            try:
                result = await coro
                if task.status != "cancelled":
                    task.status = "done"
                    task.result = str(result or "Tamamlandı")
                    task.finished_at = time.time()
                    self._pending_notifications.append(
                        f"✓ [{name}] tamamlandı ({task.elapsed}): {task.result[:80]}"
                    )
                    log.info(f"BG task done: {name} ({task.elapsed})")
            except asyncio.CancelledError:
                task.finished_at = time.time()
                log.info(f"BG task cancelled: {name}")
                raise
            except Exception as e:
                if task.status != "cancelled":
                    task.status = "failed"
                    task.error = str(e)
                    task.finished_at = time.time()
                    self._pending_notifications.append(
                        f"✗ [{name}] başarısız: {str(e)[:80]}"
                    )
                    log.error(f"BG task failed: {name}: {e}")

        asyncio_task = asyncio.create_task(_run())
        task._asyncio_task = asyncio_task
        log.info(f"BG task started: {name} ({task_id})")
        return task_id

    def pop_notifications(self) -> list[str]:
        """Get and clear finished task notifications."""
        notifs = self._pending_notifications.copy()
        self._pending_notifications.clear()
        return notifs

    def list_tasks(self) -> list[BackgroundTask]:
        """Return all tasks."""
        return list(self._tasks.values())

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a specific task by ID."""
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        """Cancel a running background task."""
        task = self.get(task_id)
        if not task or task.status != "running":
            return False
        
        task.status = "cancelled"
        task.finished_at = time.time()
        self._pending_notifications.append(f"⚠ [{task.name}] iptal edildi.")
        if task._process:
            try:
                task._process.terminate()
            except ProcessLookupError:
                pass
                
        if task._asyncio_task:
            task._asyncio_task.cancel()
            
        return True

    def clear_done(self):
        """Remove finished, failed or cancelled tasks from history."""
        self._tasks = {k: v for k, v in self._tasks.items() if v.status == "running"}

# Singleton instance
task_manager = TaskManager()
