import asyncio
import json
import threading
from tools.registry import register_tool
from bg_tools.task_manager import task_manager, BackgroundTask
from core.logger import log
from core.constants import t


@register_tool(
    name="cancel_background",
    description="Cancel a running background task by its ID.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The ID of the task to cancel."}
        },
        "required": ["task_id"]
    }
)
def cancel_background(task_id: str) -> str:
    if task_manager.cancel(task_id):
        return json.dumps({"status": "success", "message": f"Task {task_id} cancelled."})
    return json.dumps({"status": "error", "message": f"Task {task_id} not found or not running."})


@register_tool(
    name="list_background",
    description="List all background tasks and their statuses.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def list_background() -> str:
    tasks = task_manager.list_tasks()
    if not tasks:
        return json.dumps({"status": "success", "tasks": []})
        
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "elapsed": t.elapsed,
            "result": t.result[:100] if t.result else "",
            "error": t.error[:100] if t.error else ""
        })
    return json.dumps({"status": "success", "tasks": result})


def task_create_bash(command: str, label: str = "", notify_on_complete: bool = False) -> str:
    """Bir bash komutunu arka planda calistir (OS process, asyncio'dan bagimsiz)."""
    import subprocess, uuid, os, time

    task_id = uuid.uuid4().hex[:8]
    name = label or command[:30]

    # Gercek OS subprocess — asyncio'dan tamamen bagimsiz
    # Sudo komutlari icin: godmode'da -S flagi + stdin pipe
    from core.mode_manager import modes
    if command.strip().startswith("sudo ") or command.strip().startswith("/usr/bin/sudo "):
        try:
            from soul.personality import SUDO_PASSWORD
            if SUDO_PASSWORD:
                # sudo -S: stdin'den parola okur
                if command.strip().startswith("sudo "):
                    command = command.replace("sudo ", "sudo -S ", 1)
                else:
                    command = command.replace("/usr/bin/sudo ", "/usr/bin/sudo -S ", 1)
        except ImportError:
            pass

    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Sudo parolasini stdin'e yaz (sudo -S flagi eklendi)
    try:
        from soul.personality import SUDO_PASSWORD as _sudo_pwd
        if _sudo_pwd and ("sudo " in command or "sudo -S " in command):
            proc.stdin.write(f"{_sudo_pwd}\n".encode("utf-8"))
            proc.stdin.flush()
    except (ImportError, OSError, AttributeError):
        pass

    task = BackgroundTask(id=task_id, name=name, status="running")
    task._process = proc
    task_manager._tasks[task_id] = task

    log.info(f"BG task started (PID={proc.pid}): {name} ({task_id})")

    # Notification: komut bittiginde veya hata alirsa
    if notify_on_complete:
        _notif_lock = threading.Lock()

        def _notify(msg: str):
            with _notif_lock:
                task_manager._pending_notifications.append(msg)

        def _wait_and_notify():
            try:
                stdout, stderr = proc.communicate(timeout=300)
                _out = stdout.decode("utf-8", errors="replace")[:2000]
                _err = stderr.decode("utf-8", errors="replace")[:500]
                # Show output after timeout (code 124) or normal completion
                if proc.returncode in (0, 124):
                    task.status = "done"
                    task.result = _out
                    task.finished_at = time.time()
                    _preview = _out[:80] if _out.strip() else _err[:80]
                    _notify(f"✓ [{name}] completed ({task.elapsed}s): {_preview}")
                else:
                    task.status = "failed"
                    task.error = _err or _out[:500]
                    task.finished_at = time.time()
                    _preview = (_err or _out)[:80]
                    _notify(f"⚠ [{name}] exit: {_preview}")
                # Auto-clean failed tasks
                if task.status == "failed":
                    task_manager.clear_failed()
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()  # reap
                task.status = "failed"
                task.error = "timeout (300s)"
                task.finished_at = time.time()
                _notify(f"⏱ [{name}] timeout (300s)")
            except (OSError, ValueError) as e:
                task.status = "failed"
                task.error = str(e)[:200]
                task.finished_at = time.time()
                _notify(f"✗ [{name}] error: {str(e)[:80]}")

        threading.Thread(target=_wait_and_notify, daemon=True).start()

    return json.dumps({
        "status": "success",
        "task_id": task_id,
        "message": f"Task '{task_id}' baslatildi (PID={proc.pid}). notification={notify_on_complete}"
    })
