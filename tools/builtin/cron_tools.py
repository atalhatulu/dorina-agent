"""Cron job tools — one tool, 4 actions."""
from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="cron",
    description="Manage scheduled cron jobs: list/add/remove/clear/run. Jobs run either as shell commands (mode='shell', default) or as LLM-driven agent missions (mode='agent', runs the prompt via a SubAgent with its own tools).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "clear", "run"],
                "description": "Action: list (show), add (create), remove (delete), clear (delete all), run (trigger a job now)",
            },
            "name": {"type": "string", "description": "Job name (required for add)"},
            "schedule": {"type": "string", "description": "Schedule: '30m', 'every 2h', '0 9 * * *' (required for add)"},
            "prompt": {"type": "string", "description": "Prompt/command to run (required for add)"},
            "mode": {"type": "string", "enum": ["shell", "agent"], "description": "Run mode for add. 'shell' = subprocess command, 'agent' = LLM SubAgent mission (default shell)."},
            "toolsets": {
                "type": "array",
                "items": {"type": "string", "enum": ["file", "web", "terminal", "git", "memory", "research"]},
                "description": "Toolsets for agent-mode jobs (default: file, web, terminal)",
            },
            "job_id": {"type": "string", "description": "Job ID to remove or run (required for remove/run)"},
        },
        "required": ["action"],
    },
    toolset="system",
)
def cron_tool(action: str, name: str = "", schedule: str = "", prompt: str = "",
              mode: str = "shell", toolsets: list[str] | None = None, job_id: str = "") -> str:
    try:
        from cron.scheduler import cron
        if action == "list":
            jobs = cron.list_jobs()
            return json.dumps({"success": True, "jobs": [(j.name, j.schedule, j.mode) for j in jobs]}, ensure_ascii=False)
        elif action == "add":
            if not all([name, schedule, prompt]):
                return json.dumps({"error": "add requires name, schedule and prompt"})
            cron.add(name=name, schedule=schedule, prompt=prompt,
                     mode=mode, toolsets=toolsets or ["file", "web", "terminal"])
            return json.dumps({"success": True, "message": f"Job added: {name} (mode={mode})"}, ensure_ascii=False)
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
        elif action == "run":
            if not job_id:
                return json.dumps({"error": "run requires job_id"})
            job = _find_job(job_id)
            if not job:
                return json.dumps({"error": f"Job not found: {job_id}"})
            import threading
            threading.Thread(target=_execute_job_safe, args=(cron, job), daemon=True).start()
            return json.dumps({"success": True, "message": f"Job triggered: {job.name} (mode={job.mode})"}, ensure_ascii=False)
        return json.dumps({"error": f"Unknown action: {action}"})
    except (ImportError, AttributeError, OSError) as e:
        return json.dumps({"error": str(e)})


def _find_job(job_id: str):
    from cron.scheduler import cron
    for j in cron.list_jobs():
        if j.id == job_id or j.name == job_id:
            return j
    return None


def _execute_job_safe(cron_scheduler, job):
    """Trigger a job immediately in a background thread (so the tool returns fast)."""
    try:
        cron_scheduler._execute(job)
    except Exception as e:  # noqa: BLE001
        from core.logger import log
        log.error(f"Cron manual run failed [{job.name}]: {e}")
