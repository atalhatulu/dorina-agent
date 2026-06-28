"""
File History — Claude Code'dan esinlenilmiş dosya sürüm sistemi.

Her write_file/patch çağrısından ÖNCE dosyanın snapshot'ını alır.
İstenirse geri sarılabilir. Maksimum 100 snapshot tutar.
"""

from __future__ import annotations
import json
import shutil
import hashlib
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional


class FileHistory:
    """Dosya değişikliklerini snapshot'la, geri sar."""

    def __init__(self, base_dir: str | None = None):
        self.base = Path(base_dir or Path.cwd())
        self.backup_dir = self.base / ".backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.backup_dir / "index.json"
        self._index: dict = self._load_index()
        self.max_snapshots = 100

    def _load_index(self) -> dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text())
            except:
                pass
        return {"snapshots": [], "sequence": 0}

    def _save_index(self):
        # Clean old snapshots
        while len(self._index["snapshots"]) > self.max_snapshots:
            old = self._index["snapshots"].pop(0)
            old_path = self.backup_dir / old["backup"]
            if old_path.exists():
                old_path.unlink()
        self._index_path.write_text(json.dumps(self._index, indent=2))

    def snapshot_before(self, file_path: str, tool_name: str = "") -> Optional[str]:
        """
        Dosyayı değiştirmeden ÖNCE snapshot al.
        Dönen: backup dosya adı veya None (dosya yoksa)
        """
        p = Path(file_path)
        if not p.is_absolute():
            p = self.base / p
        p = p.resolve()

        if not p.exists():
            return None

        self._index["sequence"] += 1
        seq = self._index["sequence"]
        content = p.read_bytes()
        file_hash = hashlib.md5(content).hexdigest()[:12]

        # Backup filename: sequence_hash_originalname.backup
        backup_name = f"{seq:04d}_{file_hash}_{p.name}.backup"
        backup_path = self.backup_dir / backup_name
        shutil.copy2(p, backup_path)

        snapshot = {
            "backup": backup_name,
            "file": str(p),
            "time": datetime.now().isoformat(),
            "hash": file_hash,
            "size": len(content),
            "tool": tool_name,
        }
        self._index["snapshots"].append(snapshot)
        self._save_index()
        return backup_name

    def get_history(self, file_path: str = "", limit: int = 20) -> list[dict]:
        """Bir dosyanın veya tüm snapshot'ların geçmişini getir."""
        snapshots = self._index["snapshots"]
        if file_path:
            p = str(Path(file_path).resolve())
            snapshots = [s for s in snapshots if s["file"] == p]
        return snapshots[-limit:]

    def restore(self, snapshot_index: int = -1, file_path: str = "") -> Optional[str]:
        """
        Snapshot'u geri yükle.
        snapshot_index: -1 = son, -2 = sondan bir önceki...
        file_path: belirli bir dosyaysa sadece onu geri sar
        """
        snapshots = self._index["snapshots"]
        if file_path:
            p = str(Path(file_path).resolve())
            file_snaps = [s for s in snapshots if s["file"] == p]
            if not file_snaps:
                return None
            snap = file_snaps[snapshot_index] if abs(snapshot_index) <= len(file_snaps) else file_snaps[0]
        else:
            if not snapshots:
                return None
            snap = snapshots[snapshot_index] if abs(snapshot_index) <= len(snapshots) else snapshots[0]

        backup_path = self.backup_dir / snap["backup"]
        if not backup_path.exists():
            return None

        target = Path(snap["file"])
        shutil.copy2(backup_path, target)
        return snap["file"]

    def diff(self, file_path: str, snapshot_index: int = -1) -> str:
        """Mevcut dosya ile snapshot arasındaki farkı göster."""
        snapshots = self.get_history(file_path)
        if not snapshots:
            return "Snapshot yok"

        snap = snapshots[snapshot_index] if abs(snapshot_index) <= len(snapshots) else snapshots[0]
        backup_path = self.backup_dir / snap["backup"]
        if not backup_path.exists():
            return "Backup dosyasi bulunamadi"

        current = Path(snap["file"])
        if not current.exists():
            return "Dosya mevcut degil"

        old_lines = backup_path.read_text().splitlines()
        new_lines = current.read_text().splitlines()
        diff = difflib.unified_diff(old_lines, new_lines, fromfile="snapshot", tofile="current", lineterm="")
        return "\n".join(list(diff)[:50]) or "Fark yok"

    def stats(self) -> dict:
        """İstatistikler."""
        snapshots = self._index["snapshots"]
        files = set(s["file"] for s in snapshots)
        total_size = sum(s["size"] for s in snapshots)
        return {
            "total_snapshots": len(snapshots),
            "unique_files": len(files),
            "total_size_kb": round(total_size / 1024, 1),
            "oldest": snapshots[0]["time"] if snapshots else None,
            "newest": snapshots[-1]["time"] if snapshots else None,
            "sequence": self._index["sequence"],
        }


# Global instance
file_history = FileHistory()
