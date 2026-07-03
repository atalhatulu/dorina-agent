"""Memory tool — permanently save user preferences and agent notes."""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool
from core.constants import DORINA_HOME

MEMORY_DIR = DORINA_HOME / "memories"


def _ensure():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _read(target: str) -> str:
    path = MEMORY_DIR / f"{target.upper()}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write(target: str, content: str):
    _ensure()
    (MEMORY_DIR / f"{target.upper()}.md").write_text(content.strip() + "\n", encoding="utf-8")


@register_tool(
    name="save_memory",
    description="Save user preferences or learned info permanently. Never forget again. target='skill' requires the name parameter (e.g. 'html-website').",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["user", "memory", "skill"],
                "description": "'user' = USER PROFILE (age, name, language, colors, personal preferences). 'memory' = NOTES FOR YOURSELF (tool behavior, environment, project structure). 'skill' = TECHNICAL PATTERNS (website template, command sequence, solution method).",
            },
            "content": {"type": "string", "description": "The information to save. Keep it short and clear."},
            "name": {
                "type": "string",
                "description": "Only for target='skill': skill name (e.g. 'html-website', 'python-test', 'flask-api'). Keep it short and descriptive.",
            },
        },
        "required": ["target", "content"],
    },
    toolset="system",
)
def save_memory_tool(target: str, content: str, name: str | None = None) -> str:
    _ensure()
    
    if target == "skill":
        _skill_name = name or content.split(":")[0].strip() or content.split()[0].strip()
        _safe_name = _skill_name.replace(" ", "-").lower()[:40]
        _skill_dir = MEMORY_DIR.parent / "skills" / _safe_name
        
        # Scan existing skills, update if similar name exists
        _skills_root = MEMORY_DIR.parent / "skills"
        if not _skill_dir.exists() and _skills_root.exists():
            _existing_skills = [d for d in _skills_root.iterdir() if d.is_dir()]
            for _d in _existing_skills:
                if _safe_name.startswith(_d.name[:10]) or _d.name.startswith(_safe_name[:10]):
                    _skill_dir = _d
                    _safe_name = _d.name
                    break
        
        _skill_dir.mkdir(parents=True, exist_ok=True)
        _path = _skill_dir / "SKILL.md"
        
        _existing = []
        if _path.exists():
            _existing = [l for l in _path.read_text(encoding="utf-8").split("\n") if l.strip()]
        
        _existing.append(f"- {content.strip()}")
        _path.write_text("\n".join(_existing) + "\n", encoding="utf-8")
        
        _preview = content.strip()[:60]
        return json.dumps({"success": True, "message": f"Skill saved: {_safe_name}", "path": str(_path), "total": len(_existing)})
    
    path = MEMORY_DIR / f"{target.upper()}.md"
    
    existing = []
    if path.exists():
        existing = [l for l in path.read_text(encoding="utf-8").split("\n") if l.strip()]
    
    existing.append(f"- {content.strip()}")
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    _preview = content.strip()[:60]
    return json.dumps({"success": True, "message": f"Saved: {target} — {_preview}", "total": len(existing)})


@register_tool(
    name="read_memory",
    description="Read saved user preferences or agent notes.",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["user", "memory", "skill"],
                "description": "'user', 'memory' or 'skill'",
            },
        },
        "required": ["target"],
    },
    toolset="system",
)
def read_memory_tool(target: str) -> str:
    content = _read(target)
    if content:
        return json.dumps({"success": True, "target": target, "content": content, "lines": len(content.split("\n"))})
    return json.dumps({"success": True, "target": target, "content": "", "lines": 0})
