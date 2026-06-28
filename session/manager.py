"""Oturum yönetimi - SQLAlchemy ile."""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import json
import uuid

from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from core.logger import log

# P2-13: Checkpoint import
from orchestrator.checkpoint import checkpoint_manager, _list_checkpoints, _checkpoint_path

DB_PATH = Path.home() / ".dorina" / "data" / "sessions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}")
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


class SessionModel(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    title = Column(String, default="İsimsiz")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = Column(Text, default="[]")
    summary = Column(Text, default="")
    model = Column(String, default="")
    token_count = Column(Integer, default=0)
    # Genisletilmis alanlar
    tool_calls = Column(Text, default="[]")  # JSON list: [{name, args_preview, result_preview, duration}]
    token_total = Column(Integer, default=0)
    cost = Column(Integer, default=0)  # mikrodolar ($0.001 = 1)
    tags = Column(Text, default="[]")  # JSON list: ["bug-fix", "feature"]


# --- DB INITIALIZATION ---
Base.metadata.create_all(engine)
# Migration: eski DB'ye yeni kolonlari ekle (SQLAlchemy 2.x uyumlu)
from sqlalchemy import text as _text
with engine.connect() as _conn:
    for col, col_type in [("tool_calls", "TEXT DEFAULT '[]'"), ("token_total", "INTEGER DEFAULT 0"), ("cost", "INTEGER DEFAULT 0"), ("tags", "TEXT DEFAULT '[]'")]:
        try:
            _conn.execute(_text(f"ALTER TABLE sessions ADD COLUMN {col} {col_type}"))
            _conn.commit()
        except Exception:
            pass  # kolon zaten var
# -------------------------

class SessionManager:
    """Oturum CRUD işlemleri."""

    def __init__(self):
        self.db = SessionLocal()
        self.current_id: str | None = None

    def create(self, title: str = "İsimsiz", model: str = "") -> str:
        """Yeni oturum oluştur."""
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        session = SessionModel(
            id=session_id,
            title=title,
            model=model,
            messages="[]",
        )
        self.db.add(session)
        self.db.commit()
        self.current_id = session_id
        log.info(f"Yeni oturum: {session_id}")
        return session_id

    _last_messages_hash: str = ""
    _save_debounce_count: int = 0

    def save(self, messages: list[dict], summary: str = "", title: str = "",
             tool_calls_data: list[dict] = None,
             token_total: int = 0, cost: int = 0, tags: list[str] = None):
        """Save current session (only if changed)."""
        if not self.current_id:
            self.create(title=title)
        # Auto-preview from first user message
        if not summary:
            for m in messages:
                if m.get("role") == "user" and m.get("content"):
                    summary = m["content"][:100]
                    break
        if not title:
            for m in messages:
                if m.get("role") == "user" and m.get("content"):
                    title = m["content"][:50]
                    break
        # Skip if no changes (using debounce to prevent unnecessary repeats)
        import hashlib
        new_hash = hashlib.md5(str(messages).encode()).hexdigest()
        if new_hash == self._last_messages_hash:
            self._save_debounce_count += 1
            if self._save_debounce_count >= 5:
                # Force save every 5th identical call to be safe
                self._save_debounce_count = 0
            else:
                return
        else:
            self._save_debounce_count = 0
        self._last_messages_hash = new_hash
        
        session = self.db.query(SessionModel).filter_by(id=self.current_id).first()
        if session:
            session.messages = json.dumps(messages, ensure_ascii=False)
            session.summary = summary
            session.updated_at = datetime.now(timezone.utc)
            session.token_count = sum(len(str(m.get("content") or "")) for m in messages) // 4
            if tool_calls_data is not None:
                session.tool_calls = json.dumps(tool_calls_data, ensure_ascii=False)
            if token_total:
                session.token_total = token_total
            if cost:
                session.cost = cost
            if tags is not None:
                session.tags = json.dumps(tags, ensure_ascii=False)
            self.db.commit()

    def load(self, session_id: str) -> Optional[dict]:
        """Oturum yükle."""
        session = self.db.query(SessionModel).filter_by(id=session_id).first()
        if session:
            self.current_id = session_id
            return {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else "",
                "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                "summary": session.summary,
                "messages": json.loads(session.messages),
                "model": session.model,
            }
        return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """Oturumları listele."""
        sessions = (
            self.db.query(SessionModel)
            .order_by(SessionModel.updated_at.desc())
            .limit(limit)
            .all()
        )
        # Filter out sessions with no messages
        result = []
        for s in sessions:
            if not s.messages or s.messages.strip() in ("", "[]", "{}"):
                continue
            msgs = json.loads(s.messages)
            if not msgs:
                continue
            result.append({
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                "summary": s.summary,
                "model": s.model,
                "token_count": s.token_count,
                "message_count": len([m for m in json.loads(s.messages or "[]") if m.get("role") == "user"]),
            })
        
        return result

    def search(self, query: str) -> list[dict]:
        """Oturumlarda ara."""
        sessions = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.title.contains(query) |
                SessionModel.summary.contains(query) |
                SessionModel.messages.contains(query)
            )
            .order_by(SessionModel.updated_at.desc())
            .limit(10)
            .all()
        )
        return [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "summary": s.summary[:200] if s.summary else "",
            }
            for s in sessions
        ]

    def delete(self, session_id: str):
        """Oturum sil."""
        self.db.query(SessionModel).filter_by(id=session_id).delete()
        self.db.commit()
        if self.current_id == session_id:
            self.current_id = None

    def rename(self, session_id: str, title: str):
        """Oturum adını değiştir."""
        session = self.db.query(SessionModel).filter_by(id=session_id).first()
        if session:
            session.title = title
            self.db.commit()

    def cleanup_old(self, keep_last: int = 10):
        """Delete old sessions, keep only the most recent N."""
        all_sessions = self.list_sessions(limit=1000)
        if len(all_sessions) <= keep_last:
            return 0
        to_delete = all_sessions[keep_last:]
        for s in to_delete:
            self.db.query(SessionModel).filter_by(id=s["id"]).delete()
        self.db.commit()
        return len(to_delete)

    # ── P2-13: Checkpoint persistence ───────────────────────────

    async def save_session_checkpoint(
        self, messages: list[dict], summary: str = "",
        title: str = "", cp_type: str = "auto",
        name: Optional[str] = None,
    ) -> str:
        """Save a checkpoint tied to the current session.

        Args:
            messages: Full message list to checkpoint
            summary: Optional session summary
            title: Optional session title
            cp_type: 'auto' or 'manual'
            name: Optional custom checkpoint name

        Returns:
            Checkpoint name.
        """
        if not self.current_id:
            self.create(title=title or "Checkpoint")

        state_data = {
            "turn": 0,  # filled by caller
            "state": "",
            "messages": messages,
            "metadata": {
                "session_id": self.current_id,
                "summary": summary,
                "title": title,
            },
            "sm_history": [],
        }
        return await checkpoint_manager.save(state_data, name=name, cp_type=cp_type)

    async def load_latest_checkpoint(self) -> Optional[dict]:
        """Load the most recent checkpoint for the current session.

        Returns:
            Checkpoint data dict or None.
        """
        # First try to find checkpoints matching current session
        all_cps = await checkpoint_manager.list()
        if not all_cps:
            return None

        # Check if checkpoint metadata matches current session
        for cp in all_cps:
            data = await checkpoint_manager.load(cp["name"])
            if data:
                meta = data.get("metadata", {})
                cp_session_id = meta.get("session_id")
                if cp_session_id and cp_session_id == self.current_id:
                    return data

        # Fallback: return latest regardless of session
        return await checkpoint_manager.load_latest()

    async def restore_messages_from_checkpoint(self, cp_name: str) -> Optional[list[dict]]:
        """Restore messages from a named checkpoint.

        Args:
            cp_name: Checkpoint name

        Returns:
            Message list if found, None otherwise.
        """
        data = await checkpoint_manager.load(cp_name)
        if data:
            return data.get("messages", [])
        return None

    def list_checkpoints(self, cp_type: Optional[str] = None) -> list[dict]:
        """List all checkpoints, optionally filtered by type.

        Args:
            cp_type: Filter by 'auto' or 'manual'

        Returns:
            List of checkpoint summary dicts.
        """
        return _list_checkpoints()

    async def save_snapshot(
        self, messages: list[dict], summary: str = "",
        name: Optional[str] = None,
    ) -> str:
        """Save a manual snapshot (explicit user request).

        Args:
            messages: Current messages to snapshot
            summary: Optional summary
            name: Optional custom name

        Returns:
            Snapshot name.
        """
        return await self.save_session_checkpoint(
            messages, summary=summary,
            cp_type="manual", name=name,
        )

    async def auto_checkpoint(
        self, messages: list[dict], turn: int,
        interval: int = 5,
    ) -> Optional[str]:
        """Auto-checkpoint if enough turns have passed.

        Args:
            messages: Current messages
            turn: Current turn number
            interval: Checkpoint every N turns

        Returns:
            Checkpoint name if saved, None otherwise.
        """
        if turn > 0 and turn % interval == 0:
            return await self.save_session_checkpoint(
                messages, cp_type="auto",
                name=f"auto_turn{turn}",
            )
        return None


manager = SessionManager()
