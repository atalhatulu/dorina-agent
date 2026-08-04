"""Multi-session cross-reference. Finds related past sessions based on user input.

İki aşama:
  1) Title+summary hızlı tarama (tüm son session'lar, decrypt'siz, ucuz)
  2) Eşleşme YETERSİZSE, en güncel adayların mesaj GÖVDESİNİ decrypt edip
     içerikten ara — "eski konuşmada bahsedilen dosya/karar" özete düşmemiş
     olsa bile hatırlanır. Borç sınırlı (MAX_LOAD_FOR_BODY_SCAN).
"""

import re
from typing import List, Dict
from core.logger import log

RECALL_MIN_KEYWORDS = 1     # en az bu kadar puan (title/summary yoksa gövdeden)
RECALL_BODY_BOOST = 2       # gövde eşleşmesi puana eklenen katkı
MAX_LOAD_FOR_BODY_SCAN = 8  # gövde taraması için en fazla decrypt adedi


def extract_keywords(text: str) -> set[str]:
    """Extract significant keywords from query (4+ harf, stopwords hariç)."""
    words = re.findall(r'\b[a-zA-ZğüşıöçĞÜŞİÖÇ]{4,}\b', text.lower())
    stopwords = {
        "nasil", "nedir", "yapilir", "hakkinda", "lutfen", "merhaba",
        "tesekkur", "dorina", "bana", "yapar", "misin", "olustur", "calistir",
        "icin", "gibi", "gore", "neden", "niye", "hangi", "kimin", "veya", "yahut"
    }
    return {w for w in words if w not in stopwords}


def _keywords_in_text(keywords, text: str) -> int:
    t = text.lower()
    return sum(1 for kw in keywords if kw in t)


def _body_snippet(session_obj, keywords, session_id: str, limit: int = 200) -> str:
    """Session mesaj gövdesinden eşleşen snippet. Güvenli: çözülemezse '' döner."""
    try:
        from session.manager import manager
        if manager is None:
            return ""
        data = manager.load(session_id)
        if not data:
            return ""
        for m in data.get("messages", []) or []:
            content = str(m.get("content", ""))
            if any(kw in content.lower() for kw in keywords):
                return content.strip()[:limit]
    except Exception as e:
        log.debug(f"Body scan failed for {session_id}: {e}")
    return ""


def find_related_sessions(query: str, limit: int = 2) -> List[Dict]:
    keywords = extract_keywords(query)
    if not keywords:
        return []

    try:
        from session.manager import manager, SessionModel
    except ImportError:
        return []

    try:
        recent = manager.db.query(SessionModel).order_by(SessionModel.updated_at.desc()).limit(100).all()
    except Exception as e:
        log.debug(f"Cross-reference DB error: {e}")
        return []

    # Pool: tüm adaylar (score 0 dahil — gövdeyle kurtarılabilir)
    scored: list[list] = []
    for s in recent:
        if s.id == manager.current_id:
            continue
        text = f"{s.title or ''} {s.summary or ''}".lower()
        sc = _keywords_in_text(keywords, text)
        scored.append([sc, s, ""])  # [score, session, snippet]

    # Puan azalan, eşitse en güncel
    scored.sort(key=lambda x: (x[0], str(x[1].updated_at)), reverse=True)

    # Phase 2 — gövde taraması yalnızca title/summary yetersizse
    matched = sum(1 for x in scored if x[0] >= RECALL_MIN_KEYWORDS)
    if matched < limit and scored:
        by_recency = sorted(scored, key=lambda x: str(x[1].updated_at), reverse=True)
        scanned = 0
        for item in by_recency:
            if scanned >= MAX_LOAD_FOR_BODY_SCAN:
                break
            if item[0] >= RECALL_MIN_KEYWORDS:
                continue  # zaten title/summary'den bulduk
            snip = _body_snippet(item[1], keywords, item[1].id)
            scanned += 1
            if snip:
                item[0] += RECALL_BODY_BOOST
                item[2] = snip

    # Puan değişmiş olabilir — yeniden sırala
    scored.sort(key=lambda x: (x[0], str(x[1].updated_at)), reverse=True)

    results = []
    for sc, s, snip in scored:
        if sc < RECALL_MIN_KEYWORDS:
            continue
        results.append({
            "id": s.id,
            "title": s.title or "Untitled",
            "summary": s.summary or "",
            "snippet": snip or (s.summary or "")[:200],
            "date": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "Unknown",
            "score": sc,
        })
        if len(results) >= limit:
            break

    return results