"""Tests for session/manager.py — archive, prune, get_session_size."""

from __future__ import annotations
import json
import sys
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta


# ── Helpers ──────────────────────────────────────────────────────

def _make_messages(count: int) -> list[dict]:
    """Generate *count* simple message dicts."""
    msgs = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message #{i} — " + "x" * 50})
    return msgs


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def fresh_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a SessionManager backed by a temp SQLite DB.

    Patches DORINA_HOME → tmp_path so the session DB lives in a temp dir.
    Forces re-import of session.manager so module-level code re-runs.
    """
    import core.constants as consts
    monkeypatch.setattr(consts, "DORINA_HOME", tmp_path)

    # Force re-import so DB_PATH / engine use the monkey-patched HOME
    for mod in list(sys.modules.keys()):
        if "session.manager" in mod:
            del sys.modules[mod]
    from session.manager import SessionManager
    mgr = SessionManager()
    yield mgr
    mgr.db.close()


# ── Tests: get_session_size ──────────────────────────────────────

class TestGetSessionSize:
    def test_non_existent(self, fresh_manager):
        info = fresh_manager.get_session_size("does-not-exist")
        assert info == {"exists": False}

    def test_empty_session(self, fresh_manager):
        sid = fresh_manager.create()
        info = fresh_manager.get_session_size(sid)
        assert info["exists"] is True
        assert info["message_count"] == 0
        assert info["bytes_raw"] == 2  # "[]"
        assert info["bytes_encrypted"] > 0

    def test_with_messages(self, fresh_manager):
        sid = fresh_manager.create()
        msgs = _make_messages(5)
        fresh_manager.save(msgs, title="test-size")
        info = fresh_manager.get_session_size(sid)
        assert info["exists"] is True
        assert info["message_count"] == 5
        assert info["bytes_raw"] > 10
        assert info["bytes_encrypted"] > info["bytes_raw"]  # encrypted is larger

    def test_size_updates_after_save(self, fresh_manager):
        sid = fresh_manager.create()
        fresh_manager.save(_make_messages(3), title="test")
        info1 = fresh_manager.get_session_size(sid)
        fresh_manager.save(_make_messages(10), title="test")
        info2 = fresh_manager.get_session_size(sid)
        assert info1["message_count"] == 3
        assert info2["message_count"] == 10


# ── Tests: prune_session ─────────────────────────────────────────

class TestPruneSession:
    def test_non_existent(self, fresh_manager):
        result = fresh_manager.prune_session("does-not-exist", keep_last=10)
        assert result == -1

    def test_no_prune_needed(self, fresh_manager):
        sid = fresh_manager.create()
        msgs = _make_messages(3)
        fresh_manager.save(msgs, title="test")
        result = fresh_manager.prune_session(sid, keep_last=10)
        assert result == 0
        # Verify messages unchanged
        loaded = fresh_manager.load(sid)
        assert len(loaded["messages"]) == 3

    def test_prune_removes_old_messages(self, fresh_manager):
        sid = fresh_manager.create()
        msgs = _make_messages(20)
        fresh_manager.save(msgs, title="test")
        result = fresh_manager.prune_session(sid, keep_last=5)
        assert result == 15
        loaded = fresh_manager.load(sid)
        assert len(loaded["messages"]) == 5
        # Verify the LAST 5 messages are kept
        assert loaded["messages"][0]["content"].startswith("Message #15")
        assert loaded["messages"][-1]["content"].startswith("Message #19")

    def test_prune_all_but_one(self, fresh_manager):
        sid = fresh_manager.create()
        msgs = _make_messages(10)
        fresh_manager.save(msgs, title="test")
        result = fresh_manager.prune_session(sid, keep_last=1)
        assert result == 9
        loaded = fresh_manager.load(sid)
        assert len(loaded["messages"]) == 1
        assert loaded["messages"][0]["content"].startswith("Message #9")

    def test_prune_then_size_reflects(self, fresh_manager):
        sid = fresh_manager.create()
        fresh_manager.save(_make_messages(50), title="test")
        fresh_manager.prune_session(sid, keep_last=10)
        info = fresh_manager.get_session_size(sid)
        assert info["message_count"] == 10


# ── Tests: archive_old_sessions ──────────────────────────────────

class TestArchiveOldSessions:
    def test_no_old_sessions(self, fresh_manager):
        # Create a session now — it won't be old enough to archive
        sid = fresh_manager.create()
        fresh_manager.save(_make_messages(2), title="recent")
        count = fresh_manager.archive_old_sessions(days=7)
        assert count == 0  # not old enough

    def test_archive_moves_old_sessions(self, fresh_manager, tmp_path):
        from session.manager import SessionModel

        # Create a session and manually set updated_at to be old
        sid = fresh_manager.create()
        fresh_manager.save(_make_messages(2), title="old-session")

        old_time = datetime.utcnow() - timedelta(days=14)
        session = fresh_manager.db.query(SessionModel).filter_by(id=sid).first()
        session.updated_at = old_time
        fresh_manager.db.commit()

        count = fresh_manager.archive_old_sessions(days=7)
        assert count == 1

        # Verify session is gone from main DB
        loaded = fresh_manager.load(sid)
        assert loaded is None

        # Verify archive DB exists and has the session
        archive_path = tmp_path / "sessions" / "archive" / "sessions_archive.db"
        assert archive_path.exists()

        from sqlalchemy import create_engine, text as _txt
        from sqlalchemy.orm import sessionmaker
        from session.manager import Base

        arc_engine = create_engine(f"sqlite:///{archive_path}")
        arc_conn = arc_engine.connect()
        rows = arc_conn.execute(_txt("SELECT id FROM sessions WHERE id=:sid"), {"sid": sid}).fetchall()
        assert len(rows) == 1
        arc_conn.close()
        arc_engine.dispose()

    def test_archive_only_old_sessions(self, fresh_manager):
        from session.manager import SessionModel

        # Create old session
        old_sid = fresh_manager.create()
        fresh_manager.save(_make_messages(2), title="old")
        old = fresh_manager.db.query(SessionModel).filter_by(id=old_sid).first()
        old.updated_at = datetime.utcnow() - timedelta(days=14)
        fresh_manager.db.commit()

        # Create recent session
        new_sid = fresh_manager.create()
        fresh_manager.save(_make_messages(2), title="recent")

        count = fresh_manager.archive_old_sessions(days=7)
        assert count == 1  # only old one archived

        assert fresh_manager.load(old_sid) is None
        assert fresh_manager.load(new_sid) is not None


# ── Tests: integration scenarios ─────────────────────────────────

class TestIntegration:
    def test_full_workflow(self, fresh_manager):
        """Create → add messages → get size → prune → verify."""
        sid = fresh_manager.create()
        fresh_manager.rename(sid, "integration-test")
        fresh_manager.save(_make_messages(30))

        info_before = fresh_manager.get_session_size(sid)
        assert info_before["message_count"] == 30

        pruned = fresh_manager.prune_session(sid, keep_last=10)
        assert pruned == 20

        info_after = fresh_manager.get_session_size(sid)
        assert info_after["message_count"] == 10
        assert info_after["bytes_raw"] < info_before["bytes_raw"]

        loaded = fresh_manager.load(sid)
        assert loaded["title"] == "integration-test"
        assert len(loaded["messages"]) == 10
        assert loaded["messages"][0]["content"].startswith("Message #20")
        assert loaded["messages"][-1]["content"].startswith("Message #29")

    def test_multiple_sessions_independent(self, fresh_manager):
        """Prune should only affect the target session."""
        sid_a = fresh_manager.create()
        sid_b = fresh_manager.create()

        # After second create(), current_id = sid_b. Set back to sid_a for save.
        fresh_manager.current_id = sid_a
        fresh_manager.save(_make_messages(20))

        fresh_manager.current_id = sid_b
        fresh_manager.save(_make_messages(5))

        # Verify saves
        info_a_before = fresh_manager.get_session_size(sid_a)
        assert info_a_before["message_count"] == 20, \
            f"sid_a has {info_a_before['message_count']} msgs, expected 20"
        info_b_before = fresh_manager.get_session_size(sid_b)
        assert info_b_before["message_count"] == 5

        pruned = fresh_manager.prune_session(sid_a, keep_last=5)
        assert pruned == 15

        info_a = fresh_manager.get_session_size(sid_a)
        assert info_a["message_count"] == 5

        info_b = fresh_manager.get_session_size(sid_b)
        assert info_b["message_count"] == 5  # unchanged
