"""Memory tool — permanently save user preferences and agent notes."""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool
from core.constants import DORINA_HOME
from memory.paths import validated_skill_path

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
    if target not in ("user", "memory", "skill"):
        return json.dumps({"error": "Invalid memory target"})
    
    if target == "skill":
        _skill_name = name if name is not None else content.split(":")[0].strip()
        _skills_root = MEMORY_DIR.parent / "skills"
        try:
            validated_skill_path(_skills_root, _skill_name)
            _safe_name = _skill_name.strip().replace(" ", "-").lower()[:40]
            _skill_dir = validated_skill_path(_skills_root, _safe_name)
        except (ValueError, OSError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})
        
        _skill_dir.mkdir(parents=True, exist_ok=True)
        _path = _skill_dir / "SKILL.md"
        
        _existing = []
        if _path.exists():
            _existing = [l for l in _path.read_text(encoding="utf-8").split("\n") if l.strip()]
        
        _existing.append(f"- {content.strip()}")
        _path.write_text("\n".join(_existing) + "\n", encoding="utf-8")
        
        _preview = content.strip()[:60]
        return json.dumps({"success": True, "message": f"Skill saved: {_safe_name}", "path": str(_path), "total": len(_existing)})
    
    _ensure()
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
    if target not in ("user", "memory", "skill"):
        return json.dumps({"error": "Invalid memory target"})
    content = _read(target)
    if content:
        return json.dumps({"success": True, "target": target, "content": content, "lines": len(content.split("\n"))})
    return json.dumps({"success": True, "target": target, "content": "", "lines": 0})
