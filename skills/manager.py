"""Skills yöneticisi - öğrenme, kaydetme, kullanma, session-start bootstrap."""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from memory.procedural import ProceduralMemory
from core.utils import safe_json_loads
from core.logger import log
from core.constants import DORINA_HOME, DEFAULT_DATA_DIR, SKILL_TRIGGER_KEYWORDS, SKILL_AUTO_LOAD_THRESHOLD


class SkillManager:
    """Skill'leri yönet: algıla, kaydet, çağır, session-start bootstrap."""

    STATUS_FILE = DEFAULT_DATA_DIR / "skills_status.json"

    def __init__(self):
        self.procedural = ProceduralMemory()
        self.usage_data: dict = {}
        self._load_usage()
        # skills/learned/ dizinine yazma desteği
        self.learned_dir = DORINA_HOME / "skills" / "learned"
        self.learned_dir.mkdir(parents=True, exist_ok=True)

    def _load_usage(self):
        import json
        self.STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if self.STATUS_FILE.exists():
            self.usage_data = safe_json_loads(self.STATUS_FILE, {})

    def _save_usage(self):
        import json
        self.STATUS_FILE.write_text(json.dumps(self.usage_data, indent=2))

    def detect_skill_opportunity(self, user_message: str, assistant_message: str, tools_used: list[str]) -> bool:
        """Bu konuşmadan skill çıkarılabilir mi?"""
        # If multi-step operation exists
        if len(tools_used) >= 3:
            return True

        # Tekrarlanabilir desen varsa
        patterns = [
            "kur", "kurulum", "setup", "install",
            "test et", "dene", "dene ve",
            "şu adımları", "sırasıyla",
            "her seferinde", "genelde", "hep",
        ]
        msg_lower = (user_message + " " + assistant_message).lower()
        return any(p in msg_lower for p in patterns)

    def create_skill(self, name: str, description: str, steps: list[str], pitfalls: list[str] | None = None):
        """Skill oluştur ve kaydet (ProceduralMemory'e)."""
        content = f"""---
name: {name}
description: "{description}"
version: "1.0"
created_at: {datetime.now(timezone.utc).isoformat()}
---

## Steps
"""
        for i, step in enumerate(steps, 1):
            content += f"{i}. {step}\n"

        if pitfalls:
            content += "\n## Pitfalls\n"
            for pit in pitfalls:
                content += f"- {pit}\n"

        self.procedural.save_skill(name, content)
        self.usage_data[name] = {
            "created": datetime.now(timezone.utc).isoformat(),
            "use_count": 0,
        }
        self._save_usage()
        log.info(f"Skill oluşturuldu: {name}")
        return content

    def create_learned_skill(self, name: str, description: str, content: str):
        """Skill oluştur ve skills/learned/ dizinine kaydet (self-evolution için)."""
        skill_file = self.learned_dir / f"{name}.md"
        skill_file.write_text(content)
        self.usage_data[name] = {
            "created": datetime.now(timezone.utc).isoformat(),
            "use_count": 0,
        }
        self._save_usage()
        log.info(f"Learned skill kaydedildi: {name} -> {skill_file}")
        return str(skill_file)

    def use_skill(self, name: str) -> Optional[dict]:
        """Skill'i kullan (içeriğini getir)."""
        skill = self.procedural.get_skill(name)
        if skill:
            self.usage_data.setdefault(name, {"use_count": 0, "created": ""})
            self.usage_data[name]["use_count"] += 1
            self.usage_data[name]["last_used"] = datetime.now(timezone.utc).isoformat()
            self._save_usage()
        return skill

    def list_skills(self) -> list[dict]:
        """Tüm skill'leri listele (kullanım istatistikleriyle)."""
        skills = self.procedural.list_skills()
        for s in skills:
            stats = self.usage_data.get(s["name"], {})
            s["use_count"] = stats.get("use_count", 0)
            s["created"] = stats.get("created", "")
        return skills

    def delete_skill(self, name: str):
        self.procedural.delete_skill(name)
        self.usage_data.pop(name, None)
        self._save_usage()

    # ── P0-05: Session-Start Skill Bootstrap ──────────────────────

    def get_applicable_skills(self, session_context: dict | str) -> list[dict]:
        """Session context'e göre uygun skill'leri bul.

        Session context bir kullanıcı mesajı (str) veya dict olabilir.
        Keyword eşleşmesi ile ilgili skill kategorilerini tespit eder
        ve procedural memory'de kayıtlı skill'leri döndürür.

        Returns:
            List of skill dicts: [{"name": "...", "content": "...", "trigger": "..."}, ...]
        """
        # Session context'ten metin çıkar
        if isinstance(session_context, str):
            text = session_context.lower()
        elif isinstance(session_context, dict):
            # Dict'ten user message veya content alanını dene
            text = session_context.get("user_message", "") or session_context.get("content", "")
            if isinstance(text, str):
                text = text.lower()
            else:
                text = ""
        else:
            text = ""

        if not text:
            return []

        # Hangi kategorilerin eşleştiğini bul
        matched_categories = set()
        word_set = set(text.split())
        for category, keywords in SKILL_TRIGGER_KEYWORDS.items():
            # Hem kelime bazlı hem de substring match
            keyword_matches = sum(1 for kw in keywords if kw in word_set or kw in text)
            if keyword_matches >= SKILL_AUTO_LOAD_THRESHOLD:
                matched_categories.add(category)

        if not matched_categories:
            return []

        # Kayıtlı skill'lerden eşleşenleri bul
        all_skills = self.procedural.list_skills()
        applicable = []
        for skill in all_skills:
            skill_name = skill.get("name", "").lower()
            skill_desc = skill.get("description", "").lower()
            # Skill adı veya description kategoriyle eşleşiyor mu?
            for category in matched_categories:
                if category in skill_name or category in skill_desc:
                    content = self.procedural.get_skill(skill["name"])
                    if content:
                        applicable.append({
                            "name": skill["name"],
                            "content": content.get("content", "") if isinstance(content, dict) else str(content),
                            "trigger": category,
                        })
                    break

        log.info(f"Session-start: {len(applicable)} skill bulundu (categories={matched_categories})")
        return applicable

    def inject_skills_to_prompt(self, session_context: dict | str, system_prompt: str) -> str:
        """Session context'e göre skill'leri system prompt'a enjekte et.

        Returns:
            Güncellenmiş system_prompt (skill içerikleri eklenmiş)
        """
        applicable = self.get_applicable_skills(session_context)
        if not applicable:
            return system_prompt

        # Skill içeriklerini system_prompt'a ekle
        skill_sections = []
        for skill in applicable:
            skill_sections.append(
                f"## Skill: {skill['name']} ({skill['trigger']})\n{skill['content']}"
            )

        skill_text = "\n\n".join(skill_sections)
        enriched_prompt = f"{system_prompt}\n\n---\n### Loaded Skills\n{skill_text}"

        log.info(f"Skills injected: {[s['name'] for s in applicable]}")
        return enriched_prompt


skills = SkillManager()
