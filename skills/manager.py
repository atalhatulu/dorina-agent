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
        Scores each skill by keyword overlap + usage recency (skills used
        within the last 7 days rank higher; never-used skills rank lower).
        Returns top 3 matching skills.
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

        # Smart matching: score each skill by keyword overlap between the query
        # and the skill's name + description + first lines of content.
        # This replaces brittle category-keyword matching — skills without
        # frontmatter (plain Turkish files) now work too.
        query_words = set(w for w in text.split() if len(w) > 2)
        all_skills = self.procedural.list_skills()
        scored: list[tuple[int, dict]] = []
        for skill in all_skills:
            name = skill.get("name", "").lower()
            desc = (skill.get("description", "") or "").lower()
            content = (skill.get("content") or "")
            if isinstance(content, dict):
                content = content.get("content", "") or str(content)
            content = str(content).lower()
            # Search space: name + description + first 600 chars of content
            haystack = f"{name} {desc} {content[:600]}"
            hay_words = set(w for w in haystack.split() if len(w) > 2)
            hits = query_words & hay_words
            # Also substring match for compound terms (e.g. "deauth", "docker")
            substr_hits = sum(1 for kw in query_words if kw in haystack)
            score = len(hits) + substr_hits
            if score >= SKILL_AUTO_LOAD_THRESHOLD:
                # Usage recency bonus: +2 if used in last 7 days, +1 if ever used
                stats = self.usage_data.get(name, {})
                last_used = stats.get("last_used", "")
                use_count = stats.get("use_count", 0)
                if last_used:
                    try:
                        from datetime import datetime as _dt
                        last_dt = _dt.fromisoformat(last_used)
                        days_since = (datetime.now(timezone.utc) - last_dt).days
                        if days_since <= 7:
                            score += 2
                        elif use_count > 0:
                            score += 1
                    except (ValueError, TypeError):
                        pass
                scored.append((score, skill))

        if not scored:
            return []

        scored.sort(key=lambda x: -x[0])
        # Only load the top N most relevant skills to keep prompt small
        from core.constants import SKILL_MAX_LOAD
        applicable = []
        for score, skill in scored[:SKILL_MAX_LOAD]:
            content = self.procedural.get_skill(skill.get("name", ""))
            if isinstance(content, dict):
                content = content.get("content", "") or str(content)
            applicable.append({
                "name": skill.get("name", "skill"),
                "content": str(content),
                "trigger": f"score={score}",
            })
            # Track usage so archive_stale_skills can rank by real usage
            _n = skill.get("name", "")
            if _n:
                self.usage_data.setdefault(_n, {"use_count": 0, "created": ""})
                self.usage_data[_n]["use_count"] = self.usage_data[_n].get("use_count", 0) + 1
                self.usage_data[_n]["last_used"] = datetime.now(timezone.utc).isoformat()
                self._save_usage()

        log.info(f"Session-start: {len(applicable)} skills found (top matches)")
        return applicable

    def archive_stale_skills(self, days: int = 30, max_active: int = 10) -> list[str]:
        """Move stale skills (never used / unused for N days) to _archive/.

        Keeps only the most recently used `max_active` skills active.
        Returns list of archived skill names.
        """
        import shutil as _sh
        from datetime import datetime as _dt

        archive_dir = self.learned_dir.parent / "_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Never archive system dirs
        protected = {"_archive", "_agents", "_references", "learned", "store"}
        all_skills = self.procedural.list_skills()
        now = datetime.now(timezone.utc)
        archived = []

        # Sort by last_used (never used = oldest → archived first)
        def _sort_key(s):
            lu = self.usage_data.get(s["name"], {}).get("last_used", "")
            if not lu:
                return _dt.min.replace(tzinfo=timezone.utc)  # never used = oldest
            try:
                return _dt.fromisoformat(lu)
            except (ValueError, TypeError):
                return _dt.min.replace(tzinfo=timezone.utc)
        all_skills.sort(key=_sort_key)

        # Keep the most recent `max_active` active, archive the rest
        keep_names = {s["name"] for s in all_skills[-max_active:]}
        for skill in all_skills:
            name = skill["name"]
            if name in protected or name in keep_names:
                continue
            stats = self.usage_data.get(name, {})
            last_used = stats.get("last_used", "")
            use_count = stats.get("use_count", 0)
            stale = (not last_used) or (now - _dt.fromisoformat(last_used)).days > days
            if stale:
                src = self.procedural.skills_dir / name
                dst = archive_dir / name
                if src.exists() and not dst.exists():
                    try:
                        _sh.move(str(src), str(dst))
                        self.usage_data.pop(name, None)
                        archived.append(name)
                    except (OSError, ValueError):
                        pass
        if archived:
            self._save_usage()
            log.info(f"Archived {len(archived)} stale skills: {archived}")
        return archived

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
