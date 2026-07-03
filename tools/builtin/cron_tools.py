"""Cron job tools — one tool, 4 actions."""
from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="cron",
    description="Manage scheduled cron jobs: list/add/remove/clear.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "clear"],
                "description": "Action: list (show), add (create), remove (delete), clear (delete all)",
            },
            "name": {"type": "string", "description": "Job name (required for add)"},
            "schedule": {"type": "string", "description": "Schedule: '30m', 'every 2h', '0 9 * * *' (required for add)"},
            "prompt": {"type": "string", "description": "Prompt to run (required for add)"},
            "job_id": {"type": "string", "description": "Job ID to remove (required for remove)"},
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
                return json.dumps({"error": "add requires name, schedule and prompt"})
            cron.add_job(name=name, schedule=schedule, prompt=prompt)
            return json.dumps({"success": True, "message": f"Job added: {name}"}, ensure_ascii=False)
        elif action == "remove":
            if not job_id:
                return json.dumps({"error": "remove requires job_id"})
            cron.remove(job_id)
            return json.dumps({"success": True, "message": f"Job removed: {job_id}"}, ensure_ascii=False)
        elif action == "clear":
            count = len(cron.jobs)
            cron.jobs = []
            cron._save()
            return json.dumps({"success": True, "message": f"All cron jobs ({count}) cleared."}, ensure_ascii=False)
        return json.dumps({"error": f"Unknown action: {action}"})
    except (ImportError, AttributeError, OSError) as e:
        return json.dumps({"error": str(e)})
