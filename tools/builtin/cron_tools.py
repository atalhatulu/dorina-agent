"""Cron job tools — zamanlanmis gorevleri listele, ekle, sil."""
from __future__ import annotations
import json

from tools.registry import register_tool


@register_tool(
    name="cron_list",
    description="Zamanlanmis gorevleri (cron jobs) listele.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    toolset="system",
)
def cron_list_tool() -> str:
    try:
        from cron.scheduler import CronScheduler
        sched = CronScheduler()
        jobs = sched.list_jobs()
        return json.dumps({"success": True, "jobs": [(j.name, j.schedule) for j in jobs]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="cron_add",
    description="Yeni bir zamanlanmis gorev ekle.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Gorev adi"},
            "schedule": {"type": "string", "description": "Zamanlama ('30m', 'every 2h', '0 9 * * *')"},
            "prompt": {"type": "string", "description": "Calistirilacak prompt"},
        },
        "required": ["name", "schedule", "prompt"],
    },
    toolset="system",
)
def cron_add_tool(name: str, schedule: str, prompt: str) -> str:
    try:
        from cron.scheduler import CronScheduler
        sched = CronScheduler()
        result = sched.add_job(name=name, schedule=schedule, prompt=prompt)
        return json.dumps({"success": True, "message": f"Gorev eklendi: {name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="cron_remove",
    description="Bir zamanlanmis gorevi sil.",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Silinecek gorevin ID'si"},
        },
        "required": ["job_id"],
    },
    toolset="system",
)
def cron_remove_tool(job_id: str) -> str:
    try:
        from cron.scheduler import CronScheduler
        sched = CronScheduler()
        sched.remove(job_id)
        return json.dumps({"success": True, "message": f"Gorev silindi: {job_id}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
