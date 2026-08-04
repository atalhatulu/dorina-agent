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


def _is_encryption_enabled():
    try:
        from core.config import settings
        if hasattr(settings, "session") and hasattr(settings.session, "encryption"):
            return settings.session.encryption
        return False
    except ImportError:
        return False

def _encrypt(text: str) -> str:
    """Encrypt plaintext → base64 string. Returns text as-is if Fernet unavailable or disabled."""
    if not _is_encryption_enabled():
        return text
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
    if not ciphertext:
        return ciphertext
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


def _utc_now():
    return datetime.now(timezone.utc)


class SessionModel(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    title = Column(String, default="Untitled")
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
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
            
    # Initialize FTS5
    try:
        _conn.execute(_text("CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(session_id UNINDEXED, content, tokenize='unicode61')"))
        _conn.commit()
    except OperationalError:
        pass
        
    def fold_turkish(text: str) -> str:
        """Turkish lowercase and ASCII folding for FTS index."""
        if not text:
            return ""
        mapping = {
            'ç': 'c', 'Ç': 'c',
            'ğ': 'g', 'Ğ': 'g',
            'ı': 'i', 'I': 'i', 'İ': 'i', 'i̇': 'i',
            'ö': 'o', 'Ö': 'o',
            'ş': 's', 'Ş': 's',
            'ü': 'u', 'Ü': 'u',
        }
        text = text.lower()
        for k, v in mapping.items():
            text = text.replace(k, v)
        return text

    # Auto-migrate FTS: if a session is in `sessions` but not in `session_fts`, we migrate it.
    try:
        # Hızlı kontrol: Eğer sayılar eşitse hiç tarama
        s_count = _conn.execute(_text("SELECT COUNT(*) FROM sessions")).scalar() or 0
        f_count = _conn.execute(_text("SELECT COUNT(*) FROM session_fts")).scalar() or 0
        if s_count > f_count:
            # Detect unmigrated sessions
            rows = _conn.execute(_text(
                "SELECT id, messages FROM sessions WHERE id NOT IN (SELECT session_id FROM session_fts)"
            )).fetchall()
            for row in rows:
                sid, msgs_enc = row[0], row[1]
                if not msgs_enc or msgs_enc == "[]": continue
                try:
                    dec = _decrypt(msgs_enc)
                    msgs = json.loads(dec)
                    text_content = " ".join(m.get("content", "") for m in msgs if m.get("content") and isinstance(m.get("content"), str))
                    if text_content.strip():
                        folded_content = fold_turkish(text_content)
                        _conn.execute(_text("INSERT INTO session_fts(session_id, content) VALUES (:sid, :content)"), {"sid": sid, "content": folded_content})
                except Exception as e:
                    log.debug(f"FTS migration skipped for {sid}: {e}")
            _conn.commit()
    except Exception as e:
        log.error(f"FTS migration failed: {e}")
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
        hash_payload = json.dumps({
            "messages": messages,
            "summary": summary,
            "title": title,
            "tool_calls": tool_calls_data,
            "token_total": token_total,
            "cost": cost,
            "tags": tags,
        }, sort_keys=True, default=str)
        new_hash = hashlib.md5(hash_payload.encode("utf-8")).hexdigest()
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
            session.updated_at = datetime.utcnow()
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
            
            # FTS Update
            try:
                from sqlalchemy import text as _text
                text_content = " ".join(m.get("content", "") for m in messages if m.get("content") and isinstance(m.get("content"), str))
                self.db.execute(_text("DELETE FROM session_fts WHERE session_id = :sid"), {"sid": self.current_id})
                if text_content.strip():
                    # fold_turkish import/redeclare if needed, but it's defined globally above? No, it's inside the migration block context.
                    # Let's define it globally or as a static method. Wait, I'll just write the mapping here.
                    mapping = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'i̇': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'}
                    folded = text_content.lower()
                    for k, v in mapping.items():
                        folded = folded.replace(k, v)
                        
                    self.db.execute(
                        _text("INSERT INTO session_fts(session_id, content) VALUES (:sid, :content)"),
                        {"sid": self.current_id, "content": folded}
                    )
                self.db.commit()
            except Exception as e:
                log.error(f"FTS update failed: {e}")
                self.db.rollback()

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
            if s.message_count == 0:
                if not s.messages:
                    continue
                try:
                    dec = _decrypt(s.messages).strip()
                    if dec in ("", "[]", "{}"):
                        continue
                except Exception:
                    pass
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

    def search_content(self, query: str, limit: int = 5, max_sessions: int = 20) -> list[dict]:
        """Mesaj gövdesi içeriğinde ara. FTS5 kullanır."""
        from sqlalchemy import text as _text
        import re
        
        # Sadece harf ve rakam olan kelimeleri al (noktalama MATCH syntax hatasi verir)
        clean_query = re.sub(r'[^\w\s]', ' ', query)
        words = [w for w in clean_query.split() if len(w) >= 4]
        if not words:
            return []

        mapping = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'i̇': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'}
        folded_words = []
        for w in words:
            fw = w.lower()
            for k, v in mapping.items(): fw = fw.replace(k, v)
            folded_words.append('"' + fw.replace('"', '') + '"')
            
        fts_query = " OR ".join(folded_words)
        
        self._original_current_id = self.current_id
        final_results = []
        seen = set()

        try:
            # FTS5 search
            sql = """
                SELECT f.session_id, snippet(session_fts, -1, '...', '...', '...', 20) as snip, s.title, s.created_at
                FROM session_fts f
                JOIN sessions s ON f.session_id = s.id
                WHERE f.content MATCH :q
                ORDER BY rank
                LIMIT :lim
            """
            rows = self.db.execute(_text(sql), {"q": fts_query, "lim": limit * 2}).fetchall()
            
            for row in rows:
                sid, snip, title, created_at = row
                if sid == self.current_id: continue
                
                key = (sid, snip[:50])
                if key not in seen:
                    seen.add(key)
                    # Raw SQL'de SQLAlchemy tip dönüşümü yok: created_at str ya da datetime gelebilir
                    if isinstance(created_at, datetime):
                        ts = created_at.strftime("%Y-%m-%d %H:%M")
                    elif created_at:
                        ts = str(created_at)[:16]
                    else:
                        ts = "Unknown"
                    # Snippet icinden noktalama kaldirma yuzunden rol bilemiyoruz, varsayilan user
                    final_results.append({
                        "session_id": sid,
                        "title": title or "Untitled",
                        "timestamp": ts,
                        "snippet": snip.replace("\n", " "),
                        "score": 5.0,  # FTS handles ranking, give baseline score
                        "role": "user",
                        "content": snip
                    })
                    if len(final_results) >= limit:
                        break
        except Exception as e:
            log.error(f"FTS search failed: {e}")
            
        return final_results

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if a row was deleted."""
        result = self.db.query(SessionModel).filter_by(id=session_id).delete()
        self.db.commit()
        # FTS satırını da temizle (orphan birikmesin)
        try:
            from sqlalchemy import text as _text
            self.db.execute(_text("DELETE FROM session_fts WHERE session_id = :sid"), {"sid": session_id})
            self.db.commit()
        except Exception as e:
            log.debug(f"FTS delete failed: {e}")
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

    async def list_checkpoints(self, cp_type: Optional[str] = None) -> list[dict]:
        """List all checkpoints, optionally filtered by type.

        Args:
            cp_type: Filter by 'auto' or 'manual'

        Returns:
            List of checkpoint summary dicts.
        """
        return await checkpoint_manager.list(cp_type)

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
                
                # FTS cleanup
                from sqlalchemy import text as _text
                self.db.execute(_text("DELETE FROM session_fts WHERE session_id = :sid"), {"sid": s.id})
                
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

        original_len = len(messages)
        if original_len <= keep_last:
            return 0

        groups = []
        i = 0
        while i < original_len:
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tc_ids = {tc.get("id", "") for tc in msg.get("tool_calls", [])}
                group = [msg]
                i += 1
                while i < original_len and messages[i].get("role") == "tool":
                    if messages[i].get("tool_call_id", "") in tc_ids:
                        group.append(messages[i])
                        i += 1
                    else:
                        break
                groups.append(group)
            else:
                groups.append([msg])
                i += 1

        target_remove = original_len - keep_last
        removed = 0
        keep = []
        for group in groups:
            if removed < target_remove:
                removed += len(group)
            else:
                keep.extend(group)

        messages = keep

        session.messages = _encrypt(json.dumps(messages, ensure_ascii=False))
        session.updated_at = datetime.utcnow()
        self.db.commit()
        # FTS index'ini budanmış içerikle eşitle (stale recall olmasın)
        try:
            from sqlalchemy import text as _text
            text_content = " ".join(
                m.get("content", "") for m in messages
                if m.get("content") and isinstance(m.get("content"), str)
            )
            self.db.execute(_text("DELETE FROM session_fts WHERE session_id = :sid"), {"sid": session_id})
            if text_content.strip():
                self.db.execute(
                    _text("INSERT INTO session_fts(session_id, content) VALUES (:sid, :content)"),
                    {"sid": session_id, "content": text_content},
                )
            self.db.commit()
        except Exception as e:
            log.debug(f"FTS prune sync failed: {e}")
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
