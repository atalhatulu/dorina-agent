import asyncio
import json
from tools.registry import register_tool
from bg_tools.task_manager import task_manager


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


@register_tool(
    name="task_create_bash",
    description="Bir bash komutunu arka planda calistir. sleep, ping gibi uzun sureli komutlar icin.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Calistirilacak bash komutu"},
            "label": {"type": "string", "description": "Task etiketi", "default": ""},
        },
        "required": ["command"]
    }
)
def task_create_bash(command: str, label: str = "") -> str:
    """Bir bash komutunu arka planda calistir."""
    from bg_tools.task_manager import task_manager
    task = task_manager.create(command, label=label or command[:30])
    return json.dumps({
        "status": "success",
        "task_id": task.id,
        "message": f"Task '{task.id}' baslatildi: {command[:100]}"
    })
