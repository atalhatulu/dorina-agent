"""
Doğrulama önbelleği — test sonuçlarını hash'lerle sakla.
Sadece dosya değiştiğinde yeniden test et.
"""

import json
import hashlib
from pathlib import Path


class VerifyCache:
    def __init__(self):
        self.db_file = Path(__file__).parent.parent / "data" / ".verify_cache.json"
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict = {}
        self._load()

    def _load(self):
        if self.db_file.exists():
            try:
                self._cache = json.loads(self.db_file.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                self._cache = {}

    def _save(self):
        self.db_file.write_text(json.dumps(self._cache, indent=2))

    def _file_hash(self, path: str) -> str:
        p = Path(path)
        if p.exists():
            return hashlib.md5(p.read_bytes()).hexdigest()[:12]
        return ""

    def needs_test(self, key: str, files: list[str]) -> bool:
        """Bu testin tekrar çalıştırılması gerekli mi?"""
        if key not in self._cache:
            return True  # Hiç çalışmamış
        cached = self._cache[key]
        for f in files:
            fhash = self._file_hash(f)
            cached_hash = cached.get("files", {}).get(f, "")
            if fhash != cached_hash:
                return True  # Dosya değişmiş
        return False  # Her şey aynı, test gerekmez

    def mark_passed(self, key: str, files: list[str]):
        """Test geçti olarak işaretle."""
        self._cache[key] = {
            "files": {f: self._file_hash(f) for f in files},
            "status": "passed",
        }
        self._save()

    def status(self, key: str) -> str:
        """Son bilinen durum."""
        return self._cache.get(key, {}).get("status", "unknown")


# Global instance
cache = VerifyCache()
