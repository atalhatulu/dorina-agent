"""Prosedürel bellek - skill'leri yükler ve çalıştırır."""

from pathlib import Path
from typing import Optional
import yaml

from core.logger import log


class ProceduralMemory:
    """Skill'leri (SKILL.md) yükler ve yönetir."""

    def __init__(self, skills_dir: str = "skills/store"):
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

    def get_skill(self, name: str) -> Optional[dict]:
        """Skill içeriğini getir."""
        skill_file = self.skills_dir / name / "SKILL.md"
        if skill_file.exists():
            return self._read_skill_full(skill_file)
        return None

    def save_skill(self, name: str, content: str):
        """Skill kaydet."""
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        with open(skill_file, "w") as f:
            f.write(content)
        log.info(f"Skill kaydedildi: {name}")

    def delete_skill(self, name: str):
        """Skill sil."""
        skill_dir = self.skills_dir / name
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir)
            log.info(f"Skill silindi: {name}")

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
                except:
                    pass
        
        return info

    def _read_skill_full(self, path: Path) -> dict:
        """SKILL.md'nin tamamını oku."""
        info = self._read_skill_info(path)
        info["content"] = path.read_text()
        return info


procedural = ProceduralMemory()
