"""Önbellek — disk/RAM tabanlı sorgu önbelleği."""
from __future__ import annotations
import json
import time
from pathlib import Path

class DiskCache:
    def __init__(self, ttl: int = 3600):
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def get(self, key: str) -> str | None:
        path = self.cache_dir / f"{hash(key)}.json"
        if path.exists() and time.time() - path.stat().st_mtime < self.ttl:
            return json.loads(path.read_text())
        return None

    def set(self, key: str, value):
        path = self.cache_dir / f"{hash(key)}.json"
        path.write_text(json.dumps(value))
