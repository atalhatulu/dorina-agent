"""Cron scheduler — scheduled task manager.

Inspired by Hermes Agent's cron/scheduler.py pattern.
Simple file-based scheduler: checks every second, runs due jobs.

Two execution modes per job:
  - mode="shell"  (default): runs `prompt` as a shell command (legacy).
  - mode="agent"  : runs `prompt` as the goal of a real SubAgent, so the
                    scheduled job is an LLM-driven agent mission (with its
                    own tool loops) rather than a raw subprocess.
"""
from __future__ import annotations
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

from core.logger import log
from core.utils import safe_json_loads

from core.constants import DEFAULT_DATA_DIR
JOBS_FILE = DEFAULT_DATA_DIR / "cron_jobs.json"


@dataclass
class CronJob:
    id: str
    name: str
    schedule: str  # "30m", "2h", "daily", "0 9 * * *"
    prompt: str
    mode: str = "shell"  # "shell" | "agent"
    toolsets: list[str] = field(default_factory=lambda: ["file", "web", "terminal"])
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True
    run_count: int = 0


class CronScheduler:
    """File-based cron scheduler with shell and LLM-agent job modes."""

    def __init__(self):
        self.lock = threading.RLock()
        self.jobs: list[CronJob] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        with self.lock:
            if JOBS_FILE.exists():
                data = safe_json_loads(JOBS_FILE, [])
                for j in data:
                    try:
                        self.jobs.append(CronJob(**j))
                    except TypeError:
                        # Unknown/legacy keys — coerce into a CronJob
                        self.jobs.append(_coerce_job(j))

    def _save(self):
        with self.lock:
            data = [{
                "id": j.id, "name": j.name, "schedule": j.schedule,
                "prompt": j.prompt, "mode": j.mode, "toolsets": list(j.toolsets),
                "last_run": j.last_run, "next_run": j.next_run,
                "enabled": j.enabled, "run_count": j.run_count,
            } for j in self.jobs]
            JOBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def add(self, name: str, schedule: str, prompt: str,
            mode: str = "shell", toolsets: Optional[list[str]] = None) -> str:
        """Add a new cron job.

        schedule: '30m', '2h', 'daily', 'in Xs', or cron format.
        mode: 'shell' (subprocess) or 'agent' (LLM SubAgent mission).
        """
        import uuid
        if mode not in ("shell", "agent"):
            log.warning(f"Cron mode '{mode}' unknown; falling back to shell")
            mode = "shell"
        job = CronJob(
            id=uuid.uuid4().hex[:8],
            name=name,
            schedule=schedule,
            prompt=prompt,
            mode=mode,
            toolsets=(toolsets or ["file", "web", "terminal"]),
            next_run=self._calculate_next(schedule),
        )
        with self.lock:
            self.jobs.append(job)
            self._save()
        log.info(f"Cron added: {name} ({schedule}, mode={mode})")
        return job.id

    def remove(self, job_id_or_name: str):
        with self.lock:
            self.jobs = [j for j in self.jobs if j.id != job_id_or_name and j.name != job_id_or_name]
            self._save()

    def add_job(self, name: str, schedule: str, prompt: str, mode: str = "shell") -> str:
        """Alias for add() (defaults to shell mode for back-compat)."""
        return self.add(name, schedule, prompt, mode=mode)

    def update(self, job_id: str, **kwargs) -> bool:
        """Update job fields (schedule, prompt, mode, toolsets, enabled)."""
        with self.lock:
            for j in self.jobs:
                if j.id == job_id or j.name == job_id:
                    for k, v in kwargs.items():
                        if hasattr(j, k) and k != "id":
                            setattr(j, k, v)
                    if "mode" in kwargs and kwargs["mode"] == "agent" and "toolsets" not in kwargs:
                        j.toolsets = j.toolsets or ["file", "web", "terminal"]
                    if kwargs.get("schedule"):
                        j.next_run = self._calculate_next(kwargs["schedule"])
                    self._save()
                    return True
        return False

    def list_jobs(self) -> list[CronJob]:
        with self.lock:
            return list(self.jobs)

    def start(self):
        """Start the scheduler in the background."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Cron scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self._running = False

    def _loop(self):
        while self._running:
            now = datetime.now(timezone.utc).isoformat()
            with self.lock:
                jobs_copy = list(self.jobs)
            for job in jobs_copy:
                if job.enabled and job.next_run and job.next_run <= now:
                    self._execute(job)
            for _ in range(50):
                if not self._running:
                    break
                time.sleep(0.1)

    def _execute(self, job: CronJob):
        """Execute a job (shell or agent) and record the outcome."""
        log.info(f"Cron running: {job.name} (mode={job.mode})")
        with self.lock:
            job.run_count += 1
            job.last_run = datetime.now(timezone.utc).isoformat()
            job.next_run = self._calculate_next(job.schedule)
            self._save()

        output_file = JOBS_FILE.parent / f"cron_output_{job.id}.txt"
        try:
            if job.mode == "agent":
                stdout, stderr = _run_agent_job(job)
            else:
                stdout, stderr = _run_shell_job(job)
            output_file.write_text(
                f"[{job.last_run}] Job: {job.name} (mode={job.mode})\n"
                f"Prompt: {job.prompt}\n"
                f"Out: {stdout}\n"
                f"Err: {stderr}\n"
            )
        except (OSError, FileNotFoundError) as e:
            log.error(f"Cron execution error [{job.name}]: {e}")

        if job.schedule.startswith("in ") or job.schedule.startswith("once "):
            with self.lock:
                self.jobs = [j for j in self.jobs if j.id != job.id]
                self._save()

    def _calculate_next(self, schedule: str) -> str:
        """Calculate the next run time from a schedule string."""
        now = datetime.now(timezone.utc)

        if schedule.startswith("in ") or schedule.startswith("once "):
            schedule = schedule.split(" ", 1)[1]

        if schedule.endswith("s"):
            secs = int(schedule[:-1])
            return datetime.fromtimestamp(time.time() + secs, tz=timezone.utc).isoformat()
        elif schedule.endswith("m"):
            mins = int(schedule[:-1])
            return datetime.fromtimestamp(time.time() + mins * 60, tz=timezone.utc).isoformat()
        elif schedule.endswith("h"):
            hours = int(schedule[:-1])
            return datetime.fromtimestamp(time.time() + hours * 3600, tz=timezone.utc).isoformat()
        elif schedule == "daily":
            return datetime.fromtimestamp(time.time() + 86400, tz=timezone.utc).isoformat()
        else:
            return datetime.fromtimestamp(time.time() + 3600, tz=timezone.utc).isoformat()


def _run_shell_job(job: CronJob) -> tuple[str, str]:
    """Run the job as a shell command (legacy mode)."""
    import subprocess
    res = subprocess.run(job.prompt, shell=True, capture_output=True, text=True,
                         timeout=60)
    return res.stdout or "", res.stderr or ""


def _run_agent_job(job: CronJob) -> tuple[str, str]:
    """Run the job as an LLM-driven SubAgent mission.

    The cron scheduler runs in a plain daemon thread with no event loop of
    its own, so we drive the SubAgent's async loop with `asyncio.run`. Each
    run uses the job's own toolset selection, loops its own think→act turns,
    and returns a summary.
    """
    import asyncio
    from tools.delegate import SubAgent

    async def _mission():
        agent = SubAgent(
            goal=job.prompt,
            context=f"Scheduled cron job: {job.name} (mode=agent)",
            toolsets=list(job.toolsets or ["file", "web", "terminal"]),
        )
        result = await agent.run()
        status_line = f"[subagent status={agent.status}] [turns={agent.turn_count}]"
        return f"{status_line}\n{result or ''}", agent.error or ""

    result, err = asyncio.run(_mission())
    return result, err


def _coerce_job(raw: dict) -> CronJob:
    """Build a CronJob from legacy/unknown dict, ignoring unknown keys."""
    return CronJob(
        id=str(raw.get("id", "")),
        name=str(raw.get("name", "unnamed")),
        schedule=str(raw.get("schedule", "1h")),
        prompt=str(raw.get("prompt", "")),
        mode=str(raw.get("mode", "shell")),
        toolsets=list(raw.get("toolsets") or ["file", "web", "terminal"]),
        last_run=raw.get("last_run"),
        next_run=raw.get("next_run"),
        enabled=bool(raw.get("enabled", True)),
        run_count=int(raw.get("run_count", 0)),
    )


cron = CronScheduler()