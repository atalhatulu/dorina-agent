import asyncio
import json
from tools.registry import register_tool
from bg_tools.task_manager import task_manager

@register_tool(
    name="task_create_bash",
    description="ZAMANLAYICI, geri sayım veya arka plan görevleri için KESİNLİKLE BUNA KULLAN. Normal Terminal aracında 'sleep' komutu kullanarak BEKLEME YAPMA (Sistemi kilitler)! Bu araç komutu arka planda (asenkron) başlatır.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "label": {"type": "string", "description": "A short, readable label for this task (e.g., 'Downloading ISO')."}
        },
        "required": ["command"]
    }
)
def task_create_bash(command: str, label: str = "") -> str:
    """Komutu arka planda çalıştır, bitmesini bekleme."""
    import subprocess
    import threading
    import uuid
    import time
    
    # Kendi task nesnemizi manuel olusturup task_manager'a kaydediyoruz.
    task_id = uuid.uuid4().hex[:8]
    name = label or command[:40]
    
    from bg_tools.task_manager import BackgroundTask
    task = BackgroundTask(id=task_id, name=name)
    task_manager._tasks[task_id] = task
    
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        return json.dumps({"status": "error", "message": str(e)})

    # Iptal edilebilmesi icin process'i kaydediyoruz.
    task._process = proc
    task_manager._pending_notifications.append(f"▶ [{name}] basladi.")

    def _waiter():
        stdout, stderr = proc.communicate()
        if task.status == "cancelled":
            return
            
        task.finished_at = time.time()
        if proc.returncode != 0:
            task.status = "failed"
            task.error = stderr[:500] or stdout[:500]
            task_manager._pending_notifications.append(f"✗ [{name}] başarısız: {task.error[:80]}")
        else:
            task.status = "done"
            task.result = stdout[:500] or "Tamamlandı"
            task_manager._pending_notifications.append(f"✓ [{name}] tamamlandı: {task.result[:80]}")

    t = threading.Thread(target=_waiter, daemon=True)
    t.start()

    return json.dumps({
        "status": "success",
        "task_id": task_id,
        "message": f"Task '{label or command[:20]}' started in background."
    })


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
