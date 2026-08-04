"""Tests for context recall (TASKS_CONTEXT_RECALL.md)."""

import pytest
from orchestrator.recall import should_recall, score_relevance, format_recall
from session.manager import SessionManager

def test_should_recall():
    """Test should_recall logic (word count and markers)."""
    # 6 words min if no marker? The spec says:
    # "len(strip)>6 kelime VE ... VEYA (teknik sözcük)"
    # My logic: words > 6 AND has_marker OR has_marker OR has_technical
    # Actually my logic is: if len(words)>6 and has_marker -> True
    # if has_marker or has_technical -> True
    
    # 1. Past marker -> True
    assert should_recall("gecen sefer X'i nasil yaptik") is True
    assert should_recall("nasıl yapmıştık hatırlamıyorum") is True
    
    # 2. Short / greeting -> False
    assert should_recall("merhaba") is False
    assert should_recall("") is False
    
    # 3. Technical -> True
    assert should_recall("app.py dosyasina bakalim") is True
    assert should_recall("docker run komutu") is True
    assert should_recall("hata.md olustur") is True
    
    # 4. Long but no marker or technical -> False
    assert should_recall("bugun hava cok guzel disari cikip biraz dolasmak istiyorum") is False

def test_score_relevance():
    """Test that score_relevance just returns results as is (FTS handles ranking)."""
    results = [
        {"session_id": "1", "score": 1.0, "snippet": "A", "title": "A", "timestamp": "1", "role": "user"},
        {"session_id": "2", "score": 2.5, "snippet": "B", "title": "B", "timestamp": "2", "role": "user"},
    ]
    filtered = score_relevance(results, "query")
    assert len(filtered) == 2
    assert filtered[0]["session_id"] == "1"

def test_format_recall():
    """Test recall formatting and max_chars."""
    results = [
        {"session_id": "1", "title": "Sess 1", "timestamp": "2023", "role": "user", "snippet": "A" * 1000},
        {"session_id": "2", "title": "Sess 2", "timestamp": "2023", "role": "assistant", "snippet": "B" * 600},
    ]
    
    # Limit is 1500 chars. A*1000 takes ~1050 chars. B*600 takes ~650 chars.
    # Total > 1500. It should drop the second one.
    block = format_recall(results, max_chars=1500)
    assert "RECALLED CONTEXT" in block
    assert "Sess 1" in block
    assert "Sess 2" not in block

def test_search_content_empty_db(monkeypatch):
    """If DB is empty, search_content returns empty list without error."""
    class MockDB:
        def query(self, *args):
            return self
        def order_by(self, *args):
            return self
        def limit(self, *args):
            return self
        def all(self):
            return []
            
    sm = SessionManager()
    sm.db = MockDB()
    results = sm.search_content("some technical query app.py")
    assert results == []

def test_injection_mock():
    """Fake injection test to ensure string formatting works."""
    # Orchestrator does this:
    sections = []
    res = [
        {"session_id": "1", "title": "Sess 1", "timestamp": "2023", "role": "user", "snippet": "docker build", "score": 3.0}
    ]
    rel = score_relevance(res, "docker build")
    block = format_recall(rel)
    if block:
        sections.append(block)
    assert len(sections) == 1
    assert "Sess 1" in sections[0]
