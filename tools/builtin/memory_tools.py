"""Memory tool — kullanici ve agent notlarini kalici olarak kaydet."""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool

MEMORY_DIR = Path.home() / ".dorina" / "memories"


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
    description="Kullanici tercihini veya ogrendigin bir bilgiyi kalici olarak kaydet. Bir daha asla unutma. target='skill' icin name parametresi zorunludur (orn: 'html-website').",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["user", "memory", "skill"],
                "description": "'user' = KULLANICI PROFILI (yas, isim, dil, renk, kisisel tercihler). 'memory' = KENDIN ICIN NOTLAR (tool davranisi, ortam, proje yapisi). 'skill' = TEKNIK KALIPLAR (websitesi sablonu, komut dizisi, cozum yontemi).",
            },
            "content": {"type": "string", "description": "Kaydedilecek bilgi. Kisa ve net ol."},
            "name": {
                "type": "string",
                "description": "Sadece target='skill' icin: skill adi (orn: 'html-website', 'python-test', 'flask-api'). Kisa ve aciklayici olsun.",
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
        _skill_dir.mkdir(parents=True, exist_ok=True)
        _path = _skill_dir / "SKILL.md"
        
        _existing = []
        if _path.exists():
            _existing = [l for l in _path.read_text(encoding="utf-8").split("\n") if l.strip()]
        
        _existing.append(f"- {content.strip()}")
        _path.write_text("\n".join(_existing) + "\n", encoding="utf-8")
        
        _preview = content.strip()[:60]
        return json.dumps({"success": True, "message": f"Skill kaydedildi: {_safe_name}", "path": str(_path), "total": len(_existing)})
    
    path = MEMORY_DIR / f"{target.upper()}.md"
    
    existing = []
    if path.exists():
        existing = [l for l in path.read_text(encoding="utf-8").split("\n") if l.strip()]
    
    existing.append(f"- {content.strip()}")
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    _preview = content.strip()[:60]
    return json.dumps({"success": True, "message": f"Kaydedildi: {target} — {_preview}", "total": len(existing)})


@register_tool(
    name="read_memory",
    description="Kayitli kullanici tercihlerini veya agent notlarini oku.",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["user", "memory", "skill"],
                "description": "'user', 'memory' veya 'skill'",
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
