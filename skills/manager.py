"""Skills manager — learn, save, use, session-start bootstrap."""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from memory.procedural import ProceduralMemory
from core.utils import safe_json_loads
from core.logger import log
from core.constants import DORINA_HOME, DEFAULT_DATA_DIR, SKILL_TRIGGER_KEYWORDS, SKILL_AUTO_LOAD_THRESHOLD


class SkillManager:
    """Manage skills: detect, save, call, session-start bootstrap."""

    STATUS_FILE = DEFAULT_DATA_DIR / "skills_status.json"

    def __init__(self):
        self.procedural = ProceduralMemory()
        self.usage_data: dict = {}
        self._load_usage()
        # Support writing to skills/learned/ directory
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
        """Can a skill be extracted from this conversation?"""
        # If multi-step operation exists
        if len(tools_used) >= 3:
            return True

        # If repeatable pattern detected
        patterns = [
            "kur", "kurulum", "setup", "install",
            "test et", "dene", "dene ve",
            "şu adımları", "sırasıyla",
            "her seferinde", "genelde", "hep",
        ]
        msg_lower = (user_message + " " + assistant_message).lower()
        return any(p in msg_lower for p in patterns)

    def create_skill(self, name: str, description: str, steps: list[str], pitfalls: list[str] | None = None):
        """Create and save a skill (to ProceduralMemory)."""
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
        log.info(f"Skill created: {name}")
        return content

    def create_learned_skill(self, name: str, description: str, content: str):
        """Create a skill and save to skills/learned/ directory (for self-evolution)."""
        skill_file = self.learned_dir / f"{name}.md"
        skill_file.write_text(content)
        self.usage_data[name] = {
            "created": datetime.now(timezone.utc).isoformat(),
            "use_count": 0,
        }
        self._save_usage()
        log.info(f"Learned skill saved: {name} -> {skill_file}")
        return str(skill_file)

    def use_skill(self, name: str) -> Optional[dict]:
        """Use a skill (get its content)."""
        skill = self.procedural.get_skill(name)
        if skill:
            self.usage_data.setdefault(name, {"use_count": 0, "created": ""})
            self.usage_data[name]["use_count"] += 1
            self.usage_data[name]["last_used"] = datetime.now(timezone.utc).isoformat()
            self._save_usage()
        return skill

    def list_skills(self) -> list[dict]:
        """List all skills (with usage statistics)."""
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
        """Find skills matching the session context.

        Session context can be a user message (str) or dict.
        Uses keyword matching to detect relevant skill categories
        and returns skills registered in procedural memory.

        Returns:
            List of skill dicts: [{"name": "...", "content": "...", "trigger": "..."}, ...]
        """
        # Extract text from session context
        if isinstance(session_context, str):
            text = session_context.lower()
        elif isinstance(session_context, dict):
            # Try user_message or content field from dict
            text = session_context.get("user_message", "") or session_context.get("content", "")
            if isinstance(text, str):
                text = text.lower()
            else:
                text = ""
        else:
            text = ""

        if not text:
            return []

        # Find which categories match
        matched_categories = set()
        word_set = set(text.split())
        for category, keywords in SKILL_TRIGGER_KEYWORDS.items():
            # Both word-level and substring matching
            keyword_matches = sum(1 for kw in keywords if kw in word_set or kw in text)
            if keyword_matches >= SKILL_AUTO_LOAD_THRESHOLD:
                matched_categories.add(category)

        if not matched_categories:
            return []

        # Find matching skills from registered ones
        all_skills = self.procedural.list_skills()
        applicable = []
        for skill in all_skills:
            skill_name = skill.get("name", "").lower()
            skill_desc = skill.get("description", "").lower()
            # Does skill name or description match the category?
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

        log.info(f"Session-start: {len(applicable)} skills found (categories={matched_categories})")
        return applicable

    def inject_skills_to_prompt(self, session_context: dict | str, system_prompt: str) -> str:
        """Inject skills into system prompt based on session context.

        Returns:
            Updated system_prompt (with skill contents appended)
        """
        applicable = self.get_applicable_skills(session_context)
        if not applicable:
            return system_prompt

        # Append skill contents to system prompt
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
