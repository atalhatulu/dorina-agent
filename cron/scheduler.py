"""Cron scheduler — zamanlanmış görev yöneticisi.

Hermes Agent'in cron/scheduler.py deseninden esinlenilmiştir.
Basit dosya tabanlı scheduler: her saniye kontrol eder, due job'ları çalıştırır.
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
    """Basit dosya tabanlı cron scheduler."""

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
        """Yeni cron job ekle. schedule: '30m', '2h', 'daily', cron format."""
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
        log.info(f"Cron eklendi: {name} ({schedule})")
        return job.id

    def remove(self, job_id_or_name: str):
        self.jobs = [j for j in self.jobs if j.id != job_id_or_name and j.name != job_id_or_name]
        self._save()

    def add_job(self, name: str, schedule: str, prompt: str) -> str:
        """Yeni cron job ekle (add() alias'ı)."""
        return self.add(name, schedule, prompt)

    def list_jobs(self) -> list[CronJob]:
        return self.jobs

    def start(self):
        """Arka planda scheduler'ı başlat."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Cron scheduler başlatıldı")

    def stop(self):
        """Scheduler'ı durdur."""
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
        """Job'u çalıştır."""
        log.info(f"Cron çalışıyor: {job.name}")
        job.run_count += 1
        job.last_run = datetime.now(timezone.utc).isoformat()
        job.next_run = self._calculate_next(job.schedule)
        self._save()

        # Save output
        output_file = JOBS_FILE.parent / f"cron_output_{job.id}.txt"
        try:
            # Job output'u
            import subprocess
            res = subprocess.run(job.prompt, shell=True, capture_output=True, text=True)
            output_file.write_text(f"[{job.last_run}] Job: {job.name}\nPrompt: {job.prompt}\nExit: {res.returncode}\nOut: {res.stdout}\nErr: {res.stderr}\n")
        except Exception as e:
            log.error(f"Cron çalıştırma hatası [{job.name}]: {e}")

        if job.schedule.startswith("in ") or job.schedule.startswith("once "):
            self.jobs = [j for j in self.jobs if j.id != job.id]
            self._save()

    def _calculate_next(self, schedule: str) -> str:
        """Schedule'dan bir sonraki çalışma zamanını hesapla."""
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
