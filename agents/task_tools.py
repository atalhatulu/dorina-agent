"""Task system tool'lari: task olustur, listele, yonet, subagent dev.

P2-06: Subagent-Driven Development entegrasyonu:
- dev_start: yeni geliştirme oturumu başlat
- dev_status: oturum durumunu kontrol et
- dev_run: tam pipeline çalıştır
- batch_submit: batch task gönderimi
"""

from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="task_create",
    description="Yeni task oluştur. Tip: local_bash, local_agent, local_workflow, monitor, dev_session, dev_task.",
    parameters={
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Task tipi (local_bash, local_agent, local_workflow, monitor, dev_session, dev_task)"},
            "goal": {"type": "string", "description": "Task hedefi / komut"},
            "parent_id": {"type": "string", "description": "Üst task ID (opsiyonel)", "default": ""},
        },
        "required": ["type", "goal"],
    },
    toolset="tasks",
)
def task_create_tool(type: str, goal: str, parent_id: str = "") -> str:
    """Task oluştur. Dev session ve task tipleri de desteklenir."""
    from agents.task_runner import tasks as task_runner
    t = task_runner.create(type, goal, parent_id)
    return json.dumps({"id": t.id, "type": type, "status": t.status.value, "goal": goal[:60]})


@register_tool(
    name="task_list",
    description="Task'ları listele. Status filtresi: pending, running, completed, failed, killed.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "Filtre (opsiyonel)", "default": ""},
        },
    },
    toolset="tasks",
)
def task_list_tool(status: str = "") -> str:
    from agents.task_runner import tasks
    result = tasks.list(status)
    if not result:
        return json.dumps({"tasks": [], "message": "Task yok"})
    return json.dumps({"tasks": result, "stats": tasks.stats()}, ensure_ascii=False)


@register_tool(
    name="task_status",
    description="Belirli bir task'ın durumunu kontrol et.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID"},
        },
        "required": ["task_id"],
    },
    toolset="tasks",
)
def task_status_tool(task_id: str) -> str:
    from agents.task_runner import tasks
    t = tasks.get(task_id)
    if not t:
        return json.dumps({"error": f"Task bulunamadi: {task_id}"})
    return json.dumps({
        "id": t.id,
        "type": t.type.value,
        "status": t.status.value,
        "goal": t.goal[:80],
        "result": t.result[:200] if t.result else None,
        "error": t.error,
        "duration": round(t.finished_at - t.started_at, 1) if t.finished_at and t.started_at else None,
    }, ensure_ascii=False)


# ── P2-06: Batch task tools ────────────────────────────────


@register_tool(
    name="batch_submit",
    description="Birden çok task'ı batch olarak gönder. Her task: {type, goal}",
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Task tipi"},
                        "goal": {"type": "string", "description": "Task hedefi"},
                    },
                    "required": ["type", "goal"],
                },
                "description": "Task listesi (max 10)",
            },
        },
        "required": ["tasks"],
    },
    toolset="tasks",
)
def batch_submit_tool(tasks: list) -> str:
    """Batch task gönderimi. Her task paralel çalıştırılır."""
    from agents.task_runner import tasks as task_runner

    if len(tasks) > 10:
        return json.dumps({"error": "Max 10 tasks allowed per batch"})

    results = []
    for t in tasks:
        task_type = t.get("type", "local_bash")
        goal = t.get("goal", "")
        task_obj = task_runner.create(task_type, goal)
        results.append({
            "id": task_obj.id,
            "type": task_type,
            "goal": goal[:60],
            "status": task_obj.status.value,
        })

    return json.dumps({
        "batch_size": len(results),
        "tasks": results,
        "stats": task_runner.stats(),
    }, ensure_ascii=False)


@register_tool(
    name="task_batch_status",
    description="Birden çok task'ın durumunu toplu kontrol et.",
    parameters={
        "type": "object",
        "properties": {
            "task_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task ID listesi",
            },
        },
        "required": ["task_ids"],
    },
    toolset="tasks",
)
def task_batch_status_tool(task_ids: list) -> str:
    """Batch task durum sorgulama."""
    from agents.task_runner import tasks
    results = []
    for tid in task_ids:
        t = tasks.get(tid)
        if t:
            results.append({
                "id": t.id,
                "status": t.status.value,
                "goal": t.goal[:50],
                "error": t.error,
                "duration": round(t.finished_at - t.started_at, 1) if t.finished_at and t.started_at else None,
            })
        else:
            results.append({"id": tid, "error": "Task bulunamadi"})
    return json.dumps({"tasks": results}, ensure_ascii=False)


# ── P2-06: Dev pipeline tools ──────────────────────────────


@register_tool(
    name="dev_start",
    description="Yeni subagent-driven development oturumu başlat.",
    parameters={
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Geliştirme hedefi"},
        },
        "required": ["goal"],
    },
    toolset="tasks",
)
def dev_start_tool(goal: str) -> str:
    """Yeni geliştirme oturumu başlat."""
    from orchestrator.subagent_dev import dev_pipeline
    session_id = dev_pipeline.create_session(goal)
    return json.dumps({
        "session_id": session_id,
        "goal": goal[:80],
        "status": "running",
    }, ensure_ascii=False)


@register_tool(
    name="dev_status",
    description="Geliştirme oturumunun durumunu kontrol et.",
    parameters={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID"},
        },
        "required": ["session_id"],
    },
    toolset="tasks",
)
def dev_status_tool(session_id: str) -> str:
    """Dev oturum durumu."""
    from orchestrator.subagent_dev import dev_pipeline
    session = dev_pipeline.get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session bulunamadi: {session_id}"})

    task_summaries = []
    for t in session.tasks:
        task_summaries.append({
            "id": t.id,
            "status": t.status,
            "review_score": t.review_score,
            "error": t.error,
        })

    return json.dumps({
        "session_id": session.id,
        "goal": session.goal[:80],
        "status": session.status,
        "task_count": len(session.tasks),
        "tasks": task_summaries,
    }, ensure_ascii=False)


@register_tool(
    name="dev_list_sessions",
    description="Tüm geliştirme oturumlarını listele.",
    parameters={
        "type": "object",
        "properties": {},
    },
    toolset="tasks",
)
def dev_list_sessions_tool() -> str:
    """Dev session'ları listele."""
    from orchestrator.subagent_dev import dev_pipeline
    sessions = dev_pipeline.list_sessions()
    return json.dumps({"sessions": sessions}, ensure_ascii=False)
