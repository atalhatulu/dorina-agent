"""Cron job tools — tek tool, 4 islem."""
from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="cron",
    description="Zamanlanmis gorevleri (cron) yonet: listele/ekle/sil/temizle.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "clear"],
                "description": "Islem: list (goruntule), add (ekle), remove (sil), clear (hepsini sil)",
            },
            "name": {"type": "string", "description": "Gorev adi (add icin zorunlu)"},
            "schedule": {"type": "string", "description": "Zamanlama: '30m', 'every 2h', '0 9 * * *' (add icin zorunlu)"},
            "prompt": {"type": "string", "description": "Calistirilacak prompt (add icin zorunlu)"},
            "job_id": {"type": "string", "description": "Silinecek gorevin ID'si (remove icin zorunlu)"},
        },
        "required": ["action"],
    },
    toolset="system",
)
def cron_tool(action: str, name: str = "", schedule: str = "", prompt: str = "", job_id: str = "") -> str:
    try:
        from cron.scheduler import cron
        if action == "list":
            jobs = cron.list_jobs()
            return json.dumps({"success": True, "jobs": [(j.name, j.schedule) for j in jobs]}, ensure_ascii=False)
        elif action == "add":
            if not all([name, schedule, prompt]):
                return json.dumps({"error": "add icin name, schedule ve prompt gerekli"})
            cron.add_job(name=name, schedule=schedule, prompt=prompt)
            return json.dumps({"success": True, "message": f"Gorev eklendi: {name}"}, ensure_ascii=False)
        elif action == "remove":
            if not job_id:
                return json.dumps({"error": "remove icin job_id gerekli"})
            cron.remove(job_id)
            return json.dumps({"success": True, "message": f"Gorev silindi: {job_id}"}, ensure_ascii=False)
        elif action == "clear":
            count = len(cron.jobs)
            cron.jobs = []
            cron._save()
            return json.dumps({"success": True, "message": f"Tum cronlar ({count} adet) silindi."}, ensure_ascii=False)
        return json.dumps({"error": f"Bilinmeyen action: {action}"})
    except (ImportError, AttributeError, OSError) as e:
        return json.dumps({"error": str(e)})
