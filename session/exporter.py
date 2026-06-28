"""Session exporter — session'lari .md olarak ~/.dorina/sessions/YYYY/MM/ altina kaydeder."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = Path.home() / ".dorina" / "sessions"


def _ensure_dir(session_id: str) -> Path:
    """Tarihe gore klasor olustur: ~/.dorina/sessions/YYYY/MM/DD/"""
    now = datetime.now(timezone.utc)
    session_dir = BASE_DIR / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _cleanup_old():
    """MAX_SESSIONS'u gecen eski session'lari sil."""
    all_md = sorted(BASE_DIR.rglob("*.md"), key=os.path.getmtime, reverse=True)
    if len(all_md) > MAX_SESSIONS:
        for old in all_md[MAX_SESSIONS:]:
            try:
                old.unlink()
            except Exception:
                pass


def export_session(session_id: str, messages: list[dict] = None,
                   summary: str = "", title: str = "",
                   model: str = "", tool_calls_data: list[dict] = None,
                   token_total: int = 0, cost: int = 0,
                   tags: list[str] = None) -> str:
    """Session'i .md olarak disa aktar.
    
    Returns:
        md_path
    """
    session_dir = _ensure_dir(session_id)
    safe_id = session_id.replace("/", "_").replace(" ", "_")
    
    if tool_calls_data is None:
        tool_calls_data = []
    if tags is None:
        tags = []
    
    tool_counts = {}
    for tc in tool_calls_data:
        name = tc.get("name", "?")
        tool_counts[name] = tool_counts.get(name, 0) + 1
    
    now = datetime.now(timezone.utc)
    cost_str = f"${cost / 1000:.3f}" if cost else "$0.000"
    duration_min = max(1, token_total // 500) if token_total else 1
    
    title_str = title or safe_id
    
    md_lines = []
    md_lines.append(f"# {title_str}")
    md_lines.append(f"- **Tarih:** {now.strftime('%Y-%m-%d %H:%M')}")
    md_lines.append(f"- **Sure:** ~{duration_min} dk | **Token:** {token_total:,} | **Maliyet:** {cost_str}")
    md_lines.append(f"- **Model:** {model}")
    if tags:
        md_lines.append(f"- **Etiketler:** {', '.join(tags)}")
    md_lines.append("")
    
    if summary:
        md_lines.append("## Ozet")
        md_lines.append(summary)
        md_lines.append("")
    
    if tool_counts:
        md_lines.append("## Kullanilan Araclar")
        for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            md_lines.append(f"- {name} ({count}x)")
        md_lines.append("")
    
    md_lines.append("## Konusma")
    if messages:
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            
            if role == "user":
                md_lines.append("### 👤 Prompt")
                md_lines.append(content or "")
                md_lines.append("")
            elif role == "assistant":
                if tool_calls:
                    names = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        n = fn.get("name", "?")
                        a = str(fn.get("arguments", ""))[:80]
                        names.append(f"{n}(...)")
                    md_lines.append(f"### 🤖 Dorina — {', '.join(names)}")
                    md_lines.append("")
                elif content:
                    md_lines.append("### 🤖 Dorina")
                    md_lines.append(content.strip())
                    md_lines.append("")
            elif role == "tool":
                name = msg.get("name", "?")
                result = str(msg.get("content", ""))[:80]
                md_lines.append(f"  *{name}:* {result}")
    else:
        md_lines.append("(mesaj yok)")
    
    md_path = session_dir / f"{safe_id}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    
    return str(md_path)


def list_exports(limit: int = 10) -> list[dict]:
    """Disari aktarilmis session'lari listele."""
    results = []
    for f in sorted(BASE_DIR.rglob("*.md"), key=os.path.getmtime, reverse=True)[:limit]:
        results.append({
            "path": str(f),
            "name": f.stem,
            "modified": datetime.fromtimestamp(os.path.getmtime(f)).isoformat(),
        })
    return results
