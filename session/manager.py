"""Session management — SQLAlchemy + Fernet encryption."""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import json
import uuid

from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker
from core.logger import log
from core.constants import DORINA_HOME
from core.tokenizer import count_messages_tokens

# ── Fernet session key management ─────────────────────────────────
_KEY_FILE = DORINA_HOME / ".session_key"
_fernet_instance = None


def _get_fernet():
    """Load or generate the session encryption key and return a Fernet instance."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        log.warning("cryptography package missing — session encryption disabled")
        return None

    # Try secrets.yaml first
    secrets_file = DORINA_HOME / "secrets.yaml"
    if secrets_file.exists():
        try:
            import yaml
            with open(secrets_file) as f:
                secrets = yaml.safe_load(f) or {}
            key_str = secrets.get("session_key", "")
            if key_str:
                key = key_str.encode() if isinstance(key_str, str) else key_str
                # If it's a valid Fernet key (32 base64-encoded bytes), use it
                if len(key) == 44:  # standard Fernet key length
                    _fernet_instance = Fernet(key)
                    return _fernet_instance
        except (ImportError, OSError, yaml.YAMLError, ValueError, TypeError):
            pass

    # Fallback: old .session_key file
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_bytes()
        # Validate key before using; if invalid, regenerate
        try:
            _fernet_instance = Fernet(key)
            return _fernet_instance
        except (ValueError, TypeError):
            log.warning(f"Invalid session key ({_KEY_FILE}), regenerating...")
            _KEY_FILE.unlink(missing_ok=True)
            key = Fernet.generate_key()
            _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _KEY_FILE.write_bytes(key)
            log.info(f"Session encryption key regenerated: {_KEY_FILE}")
    else:
        key = Fernet.generate_key()
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_bytes(key)
        log.info(f"Session encryption key generated: {_KEY_FILE}")

    _fernet_instance = Fernet(key)
    return _fernet_instance


def _encrypt(text: str) -> str:
    """Encrypt plaintext → base64 string. Returns text as-is if Fernet unavailable."""
    f = _get_fernet()
    if f is None:
        return text
    return f.encrypt(text.encode("utf-8")).decode("utf-8")


def _decrypt(ciphertext: str) -> str:
    """Decrypt base64 string → plaintext. Returns input as-is if Fernet unavailable.

    Handles three cases:
      1. Currently encrypted (current key)  → decrypt and return
      2. Plaintext JSON (pre-encryption era) → return as-is
      3. Encrypted with old/different key    → raise ValueError (data lost)
    """
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # Not encrypted (plaintext), corrupted, or wrong key — try JSON fallback
        import json
        try:
            json.loads(ciphertext)
            return ciphertext  # It's plaintext!
        except (json.JSONDecodeError, ValueError, TypeError):
            raise ValueError("Session data encrypted with a key that is no longer available")
# ────────────────────────────────────────────────────────────────

# P2-13: Checkpoint import
from orchestrator.checkpoint import checkpoint_manager

DB_PATH = DORINA_HOME / "data" / "sessions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}")
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


class SessionModel(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    title = Column(String, default="Untitled")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = Column(Text, default="[]")
    summary = Column(Text, default="")
    model = Column(String, default="")
    token_count = Column(Integer, default=0)
    message_count = Column(Integer, default=0)
    # Extended fields
    tool_calls = Column(Text, default="[]")  # JSON list: [{name, args_preview, result_preview, duration}]
    token_total = Column(Integer, default=0)
    cost = Column(Integer, default=0)  # mikrodolar ($0.001 = 1)
    tags = Column(Text, default="[]")  # JSON list: ["bug-fix", "feature"]


# --- DB INITIALIZATION ---
Base.metadata.create_all(engine)
# Migration: add new columns to existing DB (SQLAlchemy 2.x compatible)
from sqlalchemy import text as _text
with engine.connect() as _conn:
    for col, col_type in [("tool_calls", "TEXT DEFAULT '[]'"), ("token_total", "INTEGER DEFAULT 0"), ("cost", "INTEGER DEFAULT 0"), ("tags", "TEXT DEFAULT '[]'"), ("message_count", "INTEGER DEFAULT 0")]:
        try:
            _conn.execute(_text(f"ALTER TABLE sessions ADD COLUMN {col} {col_type}"))
            _conn.commit()
        except OperationalError:
            pass
# -------------------------

class SessionManager:
    """Session CRUD operations."""

    def __init__(self):
        self.db = SessionLocal()
        self.current_id: str | None = None

    def create(self, title: str = "Untitled", model: str = "") -> str:
        """Create a new session."""
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
        log.info(f"New session: {session_id}")
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
            session.messages = _encrypt(json.dumps(messages, ensure_ascii=False))
            session.summary = summary
            session.updated_at = datetime.now(timezone.utc)
            session.token_count = count_messages_tokens(messages)
            session.message_count = len([m for m in messages if m.get("role") == "user"])
            if tool_calls_data is not None:
                session.tool_calls = _encrypt(json.dumps(tool_calls_data, ensure_ascii=False))
            if token_total:
                session.token_total = token_total
            if cost:
                session.cost = cost
            if tags is not None:
                session.tags = _encrypt(json.dumps(tags, ensure_ascii=False))
            self.db.commit()

    def load(self, session_id: str) -> Optional[dict]:
        """Load a session."""
        session = self.db.query(SessionModel).filter_by(id=session_id).first()
        if session:
            self.current_id = session_id
            return {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else "",
                "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                "summary": session.summary,
                "messages": json.loads(_decrypt(session.messages)),
                "model": session.model,
            }
        return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """List sessions."""
        sessions = (
            self.db.query(SessionModel)
            .order_by(SessionModel.updated_at.desc())
            .limit(limit)
            .all()
        )
        # Filter out sessions with no messages
        result = []
        for s in sessions:
            if s.message_count == 0 and (not s.messages or s.messages.strip() in ("", "[]", "{}")):
                continue
            result.append({
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                "summary": s.summary,
                "model": s.model,
                "token_count": s.token_count,
                "message_count": s.message_count,
            })
        
        return result

    def search(self, query: str) -> list[dict]:
        """Search sessions."""
        sessions = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.title.contains(query) |
                SessionModel.summary.contains(query)
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

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if a row was deleted."""
        result = self.db.query(SessionModel).filter_by(id=session_id).delete()
        self.db.commit()
        if self.current_id == session_id:
            self.current_id = None
        return result > 0

    def rename(self, session_id: str, title: str):
        """Rename a session."""
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
        return checkpoint_manager.list(cp_type)

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

    # ── DB optimisation: archive / prune / size ─────────────────

    def archive_old_sessions(self, days: int = 7) -> int:
        """Archive sessions older than *days* days to ~/.dorina/sessions/archive/.

        Returns the number of archived sessions.
        """
        from sqlalchemy import create_engine as _ae
        from sqlalchemy.orm import sessionmaker as _asm

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=days)

        old = (
            self.db.query(SessionModel)
            .filter(SessionModel.updated_at < cutoff)
            .all()
        )
        if not old:
            return 0

        archive_dir = DORINA_HOME / "sessions" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_db_path = archive_dir / "sessions_archive.db"

        archive_engine = _ae(f"sqlite:///{archive_db_path}")
        Base.metadata.create_all(archive_engine)
        ArchiveSession = _asm(bind=archive_engine)()

        count = 0
        for s in old:
            try:
                ArchiveSession.merge(s)
                ArchiveSession.commit()
                self.db.query(SessionModel).filter_by(id=s.id).delete()
                self.db.commit()
                count += 1
            except (OperationalError, IntegrityError) as exc:
                ArchiveSession.rollback()
                self.db.rollback()
                log.warning(f"archive failed for session {s.id}: {exc}")

        ArchiveSession.close()
        archive_engine.dispose()
        log.info(f"Archived {count} old session(s) to {archive_db_path}")
        return count

    def prune_session(self, session_id: str, keep_last: int = 100) -> int:
        """Keep only the last *keep_last* messages in a session.

        Returns the number of messages removed, or -1 if the session was not found.
        """
        session = self.db.query(SessionModel).filter_by(id=session_id).first()
        if not session:
            return -1

        try:
            messages = json.loads(_decrypt(session.messages))
        except (ValueError, json.JSONDecodeError):
            log.warning(f"prune_session({session_id}): decrypt failed")
            return -1

        if len(messages) <= keep_last:
            return 0

        removed = len(messages) - keep_last
        messages = messages[-keep_last:]

        session.messages = _encrypt(json.dumps(messages, ensure_ascii=False))
        session.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        log.info(f"Pruned {removed} message(s) from session {session_id}")
        return removed

    def get_session_size(self, session_id: str) -> dict:
        """Return size info for a session.

        Returns a dict with keys:
          - message_count: int
          - bytes_raw: int          (plaintext JSON size)
          - bytes_encrypted: int    (encrypted column size)
          - exists: bool
        If the session does not exist, returns {'exists': False}.
        """
        session = self.db.query(SessionModel).filter_by(id=session_id).first()
        if not session:
            return {"exists": False}

        msg_count = 0
        bytes_raw = 0
        try:
            decrypted = _decrypt(session.messages)
            msgs = json.loads(decrypted)
            msg_count = len(msgs)
            bytes_raw = len(decrypted.encode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            pass

        return {
            "exists": True,
            "message_count": msg_count,
            "bytes_raw": bytes_raw,
            "bytes_encrypted": len(session.messages.encode("utf-8")) if session.messages else 0,
        }


manager = SessionManager()
