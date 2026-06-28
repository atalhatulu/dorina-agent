"""Self-evolution tool: kendi kendini denetle, öğren, geliştir."""
from __future__ import annotations
import json
from tools.registry import register_tool
from core.logger import log


@register_tool(
    name="self_check",
    description="Kendi kodunu tara, hata bul, ölü kod tespit et, iyileştirme öner.",
    parameters={"type": "object", "properties": {}},
    toolset="evolution",
)
def self_check_tool() -> str:
    """Tam kendi denetimi çalıştır."""
    from evolution.self_check import evolution
    result = evolution.run_self_check()
    return json.dumps(result, ensure_ascii=False, indent=2)


@register_tool(
    name="self_learn",
    description="Kullanım desenlerinden öğren, otomatik skill oluştur.",
    parameters={"type": "object", "properties": {}},
    toolset="evolution",
)
def self_learn_tool() -> str:
    """Öğrenilen desenleri göster."""
    from evolution.self_check import evolution
    return json.dumps({
        "patterns": evolution.learned_patterns[-10:],
        "auto_skills": [p.name for p in evolution.skill_dir.glob("*.md")],
        "total_patterns": len(evolution.learned_patterns),
    }, ensure_ascii=False, indent=2)


@register_tool(
    name="self_apply_learned",
    description="Öğrenilen desenleri skills/learned/ dizinine yaz ve kaydet.",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Öğrenilen tool adı",
            },
        },
        "required": ["tool_name"],
    },
    toolset="evolution",
)
def self_apply_learned_tool(tool_name: str) -> str:
    """Öğrenilen deseni skills/learned/ dizinine yaz."""
    from evolution.self_check import evolution
    from skills.manager import skills

    # Deseni bul
    pattern = None
    for p in evolution.learned_patterns:
        if p["tool"] == tool_name:
            pattern = p
            break

    if not pattern:
        return json.dumps({"error": f"Desen bulunamadi: {tool_name}"}, ensure_ascii=False)

    content = f"""---
name: auto-{tool_name}
description: "{tool_name} tool kullanim deseni (otomatik ogrenilen)"
author: SelfEvolution
created: {pattern["discovered_at"]}
---

# Auto-Learned: {tool_name}

## Frequency
Tool '{tool_name}' {pattern["times_seen"]} kez kullanildi.

## Steps
1. {tool_name} tool'unu uygun parametrelerle çağır
2. Sonucu kontrol et
3. Hata varsa alternatif parametrelerle dene
"""
    path = skills.create_learned_skill(f"auto-{tool_name}", tool_name, content)
    return json.dumps({"status": "ok", "path": path}, ensure_ascii=False)
