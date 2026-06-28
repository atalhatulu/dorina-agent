"""Session indexer — session bittikten sonra ogrenilenleri cikarir ve semantic memory'e ekler."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

LEARNED_DIR = Path.home() / ".dorina" / "knowledge" / "learned"


def _ensure_dir():
    LEARNED_DIR.mkdir(parents=True, exist_ok=True)


def _summarize_session(messages: list[dict], tool_calls_data: list[dict]) -> str:
    """LLM ile session ozeti cikar (basit heuristic fallback ile)."""
    # Tool istatistikleri
    tool_names = set()
    for tc in tool_calls_data or []:
        tool_names.add(tc.get("name", ""))
    
    # Kullanici prompt'larindan konu cikar
    topics = set()
    for m in (messages or []):
        if m.get("role") == "user" and m.get("content"):
            text = m["content"].lower()
            for kw in ["ekle", "duzelt", "olustur", "oku", "yaz", "sil", "guncelle", "ara", "karsilastir", "analiz et"]:
                if kw in text:
                    topics.add(kw)
    
    parts = []
    if tool_names:
        parts.append(f"Kullanilan tool'lar: {', '.join(sorted(tool_names))}")
    if topics:
        parts.append(f"Konular: {', '.join(sorted(topics))}")
    
    # Ilk kullanici mesajindan konu cikar
    first_user = ""
    for m in (messages or []):
        if m.get("role") == "user" and m.get("content"):
            first_user = m["content"][:200]
            break
    
    if first_user:
        parts.append(f"Ilk prompt: {first_user}")
    
    return " | ".join(parts) if parts else "(bos session)"


def index_session(session_id: str, messages: list[dict] = None,
                  summary: str = "", title: str = "",
                  tool_calls_data: list[dict] = None,
                  tags: list[str] = None) -> str:
    """Session bittiginde ogrenilenleri ~/.dorina/knowledge/learned/ altina kaydeder.
    
    Ayrica semantic memory'e ekler (varsa).
    """
    _ensure_dir()
    
    if tool_calls_data is None:
        tool_calls_data = []
    if tags is None:
        tags = []
    
    # Ozet cikar
    learned = _summarize_session(messages, tool_calls_data)
    full_summary = summary or learned
    
    # Dosyaya kaydet
    now = datetime.now(timezone.utc)
    safe_id = session_id.replace("/", "_").replace(" ", "_")
    
    entry = {
        "session_id": session_id,
        "title": title or safe_id,
        "summary": full_summary,
        "learned": learned,
        "tags": tags,
        "tool_calls_count": len(tool_calls_data),
        "indexed_at": now.isoformat(),
    }
    
    entry_path = LEARNED_DIR / f"{safe_id}.json"
    entry_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    
    # Semantic memory'e ekle (varsa)
    try:
        from memory.semantic import semantic
        semantic.add(
            f"Session: {title or safe_id}",
            {
                "type": "session_knowledge",
                "session_id": session_id,
                "summary": full_summary,
                "learned": learned,
                "tags": json.dumps(tags),
            },
            doc_id=f"session_knowledge_{session_id}"
        )
    except Exception:
        pass  # semantic memory yoksa sessizce gec
    
    return full_summary


def search_learned(query: str, limit: int = 5) -> list[dict]:
    """Kaydedilmis ogrenilenlerde ara."""
    _ensure_dir()
    results = []
    for f in sorted(LEARNED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            if query.lower() in data.get("summary", "").lower() or \
               query.lower() in data.get("learned", "").lower() or \
               query.lower() in " ".join(data.get("tags", [])):
                results.append(data)
                if len(results) >= limit:
                    break
        except Exception:
            pass
    return results


def list_learned(limit: int = 10) -> list[dict]:
    """Ogrenilenler listesi."""
    _ensure_dir()
    results = []
    for f in sorted(LEARNED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text())
            results.append({
                "session_id": data.get("session_id", ""),
                "title": data.get("title", ""),
                "summary": data.get("summary", "")[:100],
                "tags": data.get("tags", []),
                "indexed_at": data.get("indexed_at", ""),
            })
        except Exception:
            pass
    return results
