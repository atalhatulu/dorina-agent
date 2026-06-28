"""Session exporter — session'lari .json ve .md olarak ~/.dorina/sessions/ altina kaydeder."""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

EXPORT_DIR = Path.home() / ".dorina" / "sessions"


def _ensure_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def export_session(session_id: str, messages: list[dict] = None,
                   summary: str = "", title: str = "",
                   model: str = "", tool_calls_data: list[dict] = None,
                   token_total: int = 0, cost: int = 0,
                   tags: list[str] = None) -> tuple[str, str]:
    """Session'i .json ve .md olarak disa aktar.
    
    Returns:
        (json_path, md_path)
    """
    _ensure_dir()
    safe_id = session_id.replace("/", "_").replace(" ", "_")
    
    if tool_calls_data is None:
        tool_calls_data = []
    if tags is None:
        tags = []
    
    # Tool istatistikleri
    tool_counts = {}
    for tc in tool_calls_data:
        name = tc.get("name", "?")
        tool_counts[name] = tool_counts.get(name, 0) + 1
    
    now = datetime.now(timezone.utc)
    
    # JSON export
    json_data = {
        "id": session_id,
        "title": title,
        "summary": summary,
        "model": model,
        "created_at": now.isoformat(),
        "token_total": token_total,
        "cost": cost,
        "tags": tags,
        "tool_calls": tool_calls_data,
        "tool_summary": tool_counts,
        "messages": messages or [],
    }
    json_path = EXPORT_DIR / f"{safe_id}.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
    
    # MD export
    cost_str = f"${cost / 1000:.3f}" if cost else "$0.000"
    duration_min = max(1, token_total // 500) if token_total else 1
    
    md_lines = []
    md_lines.append(f"# Session: {title or safe_id}")
    md_lines.append(f"Tarih: {now.strftime('%Y-%m-%d %H:%M')}")
    md_lines.append(f"Sure: ~{duration_min} dk | Token: {token_total:,} | Maliyet: {cost_str}")
    md_lines.append(f"Model: {model}")
    if tags:
        md_lines.append(f"Etiketler: {', '.join(tags)}")
    md_lines.append("")
    
    md_lines.append("## Ozet")
    md_lines.append(summary or "(ozet yok)")
    md_lines.append("")
    
    md_lines.append("## Kullanilan Tool'lar")
    for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"- {name} x {count}")
    if not tool_counts:
        md_lines.append("(tool kullanilmadi)")
    md_lines.append("")
    
    md_lines.append("## Konusma")
    if messages:
        for msg in messages[-20:]:  # son 20 mesaj
            role = msg.get("role", "?")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            
            if role == "user":
                preview = (content or "")[:200].replace("\n", " ")
                md_lines.append(f"**Kullanici:** {preview}")
            elif role == "assistant":
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    md_lines.append(f"**Dorina:** [tool: {', '.join(names)}]")
                elif content:
                    preview = content[:200].replace("\n", " ")
                    md_lines.append(f"**Dorina:** {preview}")
            elif role == "tool":
                continue  # tool mesajlarini atla, konusma akisini kalabalik yapmasin
    else:
        md_lines.append("(mesaj yok)")
    
    md_path = EXPORT_DIR / f"{safe_id}.md"
    md_path.write_text("\n".join(md_lines))
    
    return str(json_path), str(md_path)


def list_exports(limit: int = 10) -> list[dict]:
    """Disari aktarilmis session'lari listele."""
    _ensure_dir()
    results = []
    for f in sorted(EXPORT_DIR.glob("*.md"), key=os.path.getmtime, reverse=True)[:limit]:
        results.append({
            "path": str(f),
            "name": f.stem,
            "modified": datetime.fromtimestamp(os.path.getmtime(f)).isoformat(),
        })
    return results
