"""Tests for multi-session cross reference."""

import pytest
from datetime import datetime, timezone
from session.cross_reference import extract_keywords, find_related_sessions

def test_extract_keywords():
    """Test keyword extraction logic."""
    # Should ignore short words (< 4 chars) and stopwords
    query = "merhaba dorina, veritabanı bağlantı hatası nedir lutfen yardım et"
    keywords = extract_keywords(query)
    
    assert "veritabanı" in keywords
    assert "bağlantı" in keywords
    assert "hatası" in keywords
    assert "yardım" in keywords
    
    # Stopwords should be excluded
    assert "merhaba" not in keywords
    assert "dorina" not in keywords
    assert "nedir" not in keywords
    assert "lutfen" not in keywords
    # Short words excluded
    assert "et" not in keywords

def test_find_related_sessions_no_keywords():
    """Should return empty list if no valid keywords found."""
    assert find_related_sessions("bu ne", limit=2) == []
    assert find_related_sessions("merhaba nasil", limit=2) == []

def test_find_related_sessions_with_mock_db(monkeypatch):
    """Test session scoring with mock db."""
    
    class MockSessionModel:
        def __init__(self, id, title, summary, updated_at=None):
            self.id = id
            self.title = title
            self.summary = summary
            self.created_at = datetime.now(timezone.utc)
            self.updated_at = updated_at or self.created_at
            
    # Create some mock sessions
    s1 = MockSessionModel("sess1", "Veritabanı Kurulumu", "PostgreSQL bağlantı ayarları yapıldı")
    s2 = MockSessionModel("sess2", "Arayüz Tasarımı", "CSS renk paleti güncellendi")
    s3 = MockSessionModel("sess3", "Sunucu Hatası", "Nginx connection reset hatası çözüldü")
    mock_sessions = [s1, s2, s3]
    
    # Mock the DB query
    class MockQuery:
        def order_by(self, *args): return self
        def limit(self, *args): return self
        def all(self): return mock_sessions
        
    class MockDB:
        def query(self, *args):
            return MockQuery()
            
    class MockManager:
        db = MockDB()
        current_id = "sess4"
        
    # Apply monkeypatch to session.manager singleton (find_related_sessions bunu
    # fonksiyon içinde `from session.manager import manager` ile çeker)
    import session.manager as sm_module
    monkeypatch.setattr(sm_module, "manager", MockManager())
    
    # Test 1: Match with s1 (veritabanı, bağlantı)
    results = find_related_sessions("veritabanı bağlantı koptu", limit=2)
    assert len(results) == 1
    assert results[0]["id"] == "sess1"
    assert results[0]["score"] >= 2
    
    # Test 2: Match with s3 (sunucu, hatası)
    results2 = find_related_sessions("sunucu hatası alıyorum", limit=2)
    assert len(results2) == 1
    assert results2[0]["id"] == "sess3"
    
    # Test 3: No match
    results3 = find_related_sessions("alakasız bir konu yazıyorum", limit=2)
    assert len(results3) == 0


def test_body_scan_recovers_old_conversation_content(monkeypatch):
    """Asıl core: keyword title/summary'de YOK, mesaj gövdesinde VAR → bulunmalı."""
    from datetime import datetime, timezone

    class MockSessionModel:
        def __init__(self, id, title, summary):
            self.id = id
            self.title = title
            self.summary = summary
            now = datetime.now(timezone.utc)
            self.created_at = now
            self.updated_at = now

    # Title/summary alakasız, ama mesaj gövdesinde anahtar var
    s_old = MockSessionModel("s_legacy", "Genel Sohbet", "bugünkü görevler")

    class MockQuery:
        def order_by(self, *a): return self
        def limit(self, *a): return self
        def all(self): return [s_old]

    class MockDB:
        def query(self, *a): return MockQuery()

    class MockManager:
        db = MockDB()
        current_id = "s_current"
        def load(self, session_id):
            # decrypt edilmiş mesaj gövdesi döner
            return {"messages": [
                {"role": "user", "content": "prometheus kurulumunu export ettik, konsol 9100'de"},
                {"role": "assistant", "content": "prometheus konfigurasyonu /etc/prometheus'de"},
            ]}

    import session.manager as sm_module
    monkeypatch.setattr(sm_module, "manager", MockManager())

    results = find_related_sessions("prometheus kurulumu nerede yapildi", limit=2)
    assert len(results) >= 1, "mesaj gövdesindeki bilgi bulunamadi"
    assert results[0]["id"] == "s_legacy"
    assert "prometheus" in (results[0]["snippet"] or "").lower()
