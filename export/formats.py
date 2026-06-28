"""Export — session'ları JSON, MD, HTML olarak dışa aktar."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime


def export_json(messages: list[dict], path: str = "") -> str:
    """Session'ı JSON olarak kaydet."""
    path = path or f"export/session_{datetime.now():%Y%m%d_%H%M%S}.json"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        tool_calls = m.get("tool_calls")
        entry = {"role": role}
        if content:
            entry["content"] = content
        if tool_calls:
            entry["tool_calls"] = tool_calls
        data.append(entry)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return path


def export_markdown(messages: list[dict], path: str = "") -> str:
    """Session'ı Markdown olarak kaydet."""
    path = path or f"export/session_{datetime.now():%Y%m%d_%H%M%S}.md"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Session Export — {datetime.now():%d %B %Y}", "", "---", ""]
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if role == "user":
            lines.append(f"## 🧑 Kullanıcı\n\n{content}\n")
        elif role == "assistant":
            lines.append(f"## 🤖 Dorina\n\n{content}\n")
        elif role == "tool":
            lines.append(f"```\n🔧 {content[:300]}\n```\n")
    Path(path).write_text("\n".join(lines))
    return path


def export_html(messages: list[dict], path: str = "") -> str:
    """Session'ı HTML olarak kaydet."""
    path = path or f"export/session_{datetime.now():%Y%m%d_%H%M%S}.html"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    html = ["<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>",
            "<title>Session Export</title>",
            "<style>body{background:#1a1815;color:#f0ead8;font-family:monospace;padding:2em}",
            ".user{color:#D4622A}.dorina{color:#6bb05d}.msg{margin:1em 0;padding:1em;border-left:3px solid #D4622A}</style></head><body>",
            "<h1>Session Export</h1>"]
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        cls = "user" if role == "user" else "dorina" if role == "assistant" else "tool"
        html.append(f"<div class='msg {cls}'><strong>{role}:</strong><br>{content}</div>")
    html.append("</body></html>")
    Path(path).write_text("\n".join(html))
    return path
