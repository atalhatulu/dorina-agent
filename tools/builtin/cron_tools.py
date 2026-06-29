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
        from cron.scheduler import cron
        jobs = cron.list_jobs()
        return json.dumps({"success": True, "jobs": [(j.name, j.schedule) for j in jobs]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="cron_add",
    description="SADECE TEKRARLAYAN/PERİYODİK (her saat, her gün vs.) görevler için kullan! Kullanıcı '1 saat sonra', '30 sn sonra' veya 'tek seferlik' diyorsa BUNU KULLANMA, 'task_create_bash' (sleep) kullan.",
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
        from cron.scheduler import cron
        result = cron.add_job(name=name, schedule=schedule, prompt=prompt)
        return json.dumps({"success": True, "message": f"Gorev eklendi: {name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="cron_remove",
    description="Bir zamanlanmis gorevi sil. job_id_or_name alanına görevin ID'sini veya adını verebilirsin.",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Silinecek gorevin ID'si veya adı"},
        },
        "required": ["job_id"],
    },
    toolset="system",
)
def cron_remove_tool(job_id_or_name: str) -> str:
    try:
        from cron.scheduler import cron
        cron.remove(job_id_or_name)
        return json.dumps({"success": True, "message": f"Gorev silindi: {job_id_or_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="cron_clear",
    description="Tüm zamanlanmış görevleri (cronları) siler. Kullanıcı 'tüm cronları sil' veya 'temizle' derse, Linux crontab YERİNE bu aracı kullan!",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    toolset="system",
)
def cron_clear_tool() -> str:
    try:
        from cron.scheduler import cron
        count = len(cron.jobs)
        cron.jobs = []
        cron._save()
        return json.dumps({"success": True, "message": f"Tüm cronlar ({count} adet) silindi."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

