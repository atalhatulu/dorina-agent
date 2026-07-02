"""Prosedürel bellek - skill'leri yükler ve çalıştırır."""

import shutil
from pathlib import Path
from typing import Any, Optional
import yaml

from core.logger import log
from core.constants import DORINA_HOME
from memory.base import BaseMemory


class ProceduralMemory(BaseMemory):
    """Skill'leri (SKILL.md) yükler ve yönetir."""

    memory_type = "procedural"

    def __init__(self, skills_dir: str | Path | None = None):
        super().__init__()
        if skills_dir is None:
            self.skills_dir = DORINA_HOME / "skills"
        else:
            self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def list_skills(self) -> list[dict]:
        """Tüm skill'leri listele."""
        skills = []
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    info = self._read_skill_info(skill_file)
                    skills.append(info)
        return skills

    # ── BaseMemory uyumluluk methodlari ────────────────────────

    def add(self, key: str, content: str, metadata: Optional[dict] = None) -> None:
        """BaseMemory uyumlu: key=skill_adi, content=icerik."""
        self.save_skill(name=key, content=content)

    def get(self, key: str) -> Any:
        """BaseMemory uyumlu: key ile skill getir."""
        skill = self.get_skill(key)
        return skill.get("content") if skill else None

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Skill adi ve iceriginde ara."""
        results = []
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            content = skill_file.read_text()
            if query.lower() in content.lower() or query.lower() in skill_dir.name.lower():
                results.append({
                    "name": skill_dir.name,
                    "content": content,
                    "path": str(skill_file),
                })
                if len(results) >= n_results:
                    break
        return results

    def delete(self, key: str) -> bool:
        """BaseMemory uyumlu: key ile skill sil."""
        try:
            skill_path = self._sanitize_name(key)
        except ValueError:
            return False
        if skill_path.exists():
            shutil.rmtree(skill_path)
            log.info(f"Skill silindi: {key}")
            return True
        return False

    def clear(self):
        """BaseMemory uyumlu: tum skill'leri temizle."""
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                shutil.rmtree(skill_dir)

    def count(self) -> int:
        """BaseMemory uyumlu: skill sayisi."""
        return len(self.list_skills())

    # ── Orijinal ProceduralMemory API ──────────────────────────

    def _sanitize_name(self, name: str) -> Path:
        """Skill adini dogrula ve path traversal'i engelle.

        Raises:
            ValueError: name '../' veya '/' iceriyorsa.
        """
        if not name or ".." in name or "/" in name or "\\" in name:
            raise ValueError(f"Guvenlik: skill adi gecersiz: '{name}'")
        return self.skills_dir / name

    def get_skill(self, name: str) -> Optional[dict]:
        """Skill içeriğini getir."""
        try:
            skill_path = self._sanitize_name(name)
        except ValueError:
            return None
        skill_file = skill_path / "SKILL.md"
        if skill_file.exists():
            return self._read_skill_full(skill_file)
        return None

    def save_skill(self, name: str, content: str):
        """Skill kaydet."""
        try:
            skill_path = self._sanitize_name(name)
        except ValueError as e:
            log.warning(str(e))
            return
        skill_path.mkdir(parents=True, exist_ok=True)
        skill_file = skill_path / "SKILL.md"
        with open(skill_file, "w") as f:
            f.write(content)
        log.info(f"Skill kaydedildi: {name}")

    def delete_skill(self, name: str):
        """Skill sil (delegates to delete)."""
        self.delete(name)

    def _read_skill_info(self, path: Path) -> dict:
        """SKILL.md başlık bilgilerini oku."""
        content = path.read_text()
        info = {"name": path.parent.name, "description": "", "path": str(path)}
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                    info["name"] = meta.get("name", info["name"])
                    info["description"] = meta.get("description", "")
                    info["version"] = meta.get("version", "1.0")
                except (KeyError, TypeError, AttributeError):
                    pass
        
        return info

    def _read_skill_full(self, path: Path) -> dict:
        """SKILL.md'nin tamamını oku."""
        info = self._read_skill_info(path)
        info["content"] = path.read_text()
        return info


procedural = ProceduralMemory()
