"""Session yöneticisi testleri."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSessionManager:
    def test_create_and_list(self):
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("test session")
        # Add a message so list_sessions includes it
        mgr.save([{"role": "user", "content": "test"}], "test")
        sessions = mgr.list_sessions()
        assert len(sessions) >= 1
        mgr.delete(sid)

    def test_save_and_load(self):
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("test")
        messages = [{"role": "user", "content": "selam"},
                    {"role": "assistant", "content": "merhaba"}]
        mgr.save(messages, "özet")
        loaded = mgr.load(sid)
        assert loaded is not None
        assert len(loaded["messages"]) == 2
        mgr.delete(sid)

    def test_search(self):
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("benzersiz_test_oturumu")
        mgr.save([{"role": "user", "content": "test mesajı"}], "özet")
        results = mgr.search("benzersiz")
        assert len(results) >= 1
        mgr.delete(sid)

    def test_rename(self):
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("eski_ad")
        mgr.rename(sid, "yeni_ad")
        loaded = mgr.load(sid)
        assert loaded["title"] == "yeni_ad"
        mgr.delete(sid)

    def test_delete(self):
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("silinecek")
        mgr.delete(sid)
        assert mgr.load(sid) is None

    def test_save_with_extra_fields(self):
        """Session manager yeni alanlari kaydediyor mu?"""
        from session.manager import SessionManager
        mgr = SessionManager()
        sid = mgr.create("test_extra")
        mgr.save(
            messages=[{"role": "user", "content": "test"}],
            tool_calls_data=[{"name": "read_file", "args_preview": "test.py"}],
            token_total=1500,
            cost=5,
            tags=["bug-fix", "test"],
        )
        # Direkt DB'den kontrol
        from sqlalchemy import text
        from session.manager import engine as _mgr_engine
        with _mgr_engine.connect() as conn:
            row = conn.execute(text(f"SELECT tool_calls, token_total, cost, tags FROM sessions WHERE id='{sid}'")).fetchone()
            assert row is not None
            # Session verisi Fernet sifreli, decryption ile kontrol et
            from session.manager import _decrypt
            decrypted = _decrypt(row[0])
            assert "read_file" in decrypted
            assert row[1] == 1500
            assert row[2] == 5
            # Tags da Fernet sifreli olabilir
            from session.manager import _decrypt as _decrypt2
            assert "bug-fix" in _decrypt2(row[3])
        mgr.delete(sid)

    def test_export_session(self):
        """Exporter calisiyor mu?"""
        from session.exporter import export_session, list_exports
        import tempfile, os
        
        md_path = export_session(
            session_id="test_export_123",
            messages=[{"role": "user", "content": "test"}],
            summary="Test ozeti",
            title="Test Session",
            model="deepseek/test",
            tool_calls_data=[{"name": "terminal", "args_preview": "ls"}],
            token_total=500,
        )
        assert os.path.exists(md_path)
        assert md_path.endswith(".md")
        # Temizlik
        os.unlink(md_path)
        _dir = os.path.dirname(md_path)
        if _dir and not os.listdir(_dir):
            os.rmdir(_dir)
