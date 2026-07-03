"""Cron scheduler — scheduled task manager.

Inspired by Hermes Agent's cron/scheduler.py pattern.
Simple file-based scheduler: checks every second, runs due jobs.
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
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True
    run_count: int = 0


class CronScheduler:
    """Simple file-based cron scheduler."""

    def __init__(self):
        self.jobs: list[CronJob] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if JOBS_FILE.exists():
            data = safe_json_loads(JOBS_FILE, [])
            self.jobs = [CronJob(**j) for j in data]

    def _save(self):
        data = [{"id": j.id, "name": j.name, "schedule": j.schedule,
                 "prompt": j.prompt, "last_run": j.last_run,
                 "next_run": j.next_run, "enabled": j.enabled,
                 "run_count": j.run_count} for j in self.jobs]
        JOBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def add(self, name: str, schedule: str, prompt: str) -> str:
        """Add new cron job. schedule: '30m', '2h', 'daily', cron format."""
        import uuid
        job = CronJob(
            id=uuid.uuid4().hex[:8],
            name=name,
            schedule=schedule,
            prompt=prompt,
            next_run=self._calculate_next(schedule),
        )
        self.jobs.append(job)
        self._save()
        log.info(f"Cron added: {name} ({schedule})")
        return job.id

    def remove(self, job_id_or_name: str):
        self.jobs = [j for j in self.jobs if j.id != job_id_or_name and j.name != job_id_or_name]
        self._save()

    def add_job(self, name: str, schedule: str, prompt: str) -> str:
        """Add new cron job (alias for add())."""
        return self.add(name, schedule, prompt)

    def list_jobs(self) -> list[CronJob]:
        return self.jobs

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
            for job in self.jobs:
                if job.enabled and job.next_run and job.next_run <= now:
                    self._execute(job)
            for _ in range(50):
                if not self._running:
                    break
                time.sleep(0.1)

    def _execute(self, job: CronJob):
        """Execute a job."""
        log.info(f"Cron running: {job.name}")
        job.run_count += 1
        job.last_run = datetime.now(timezone.utc).isoformat()
        job.next_run = self._calculate_next(job.schedule)
        self._save()

        # Save output
        output_file = JOBS_FILE.parent / f"cron_output_{job.id}.txt"
        try:
            # Job output
            import subprocess
            res = subprocess.run(job.prompt, shell=True, capture_output=True, text=True)
            output_file.write_text(f"[{job.last_run}] Job: {job.name}\nPrompt: {job.prompt}\nExit: {res.returncode}\nOut: {res.stdout}\nErr: {res.stderr}\n")
        except (OSError, FileNotFoundError) as e:
            log.error(f"Cron execution error [{job.name}]: {e}")

        if job.schedule.startswith("in ") or job.schedule.startswith("once "):
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


cron = CronScheduler()
