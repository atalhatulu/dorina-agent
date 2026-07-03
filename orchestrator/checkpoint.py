"""Checkpoint/Snapshot system — store agent state in SQLite.

Auto-checkpoints every N turns, manual snapshots via command.
Previously wrote to JSON files (P2-24), now uses SQLite.
"""

from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from core.logger import log
from core.constants import DEFAULT_DATA_DIR

# SQLite database path
DB_PATH = DEFAULT_DATA_DIR / "checkpoints.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Default: checkpoint every N turns
AUTO_CHECKPOINT_INTERVAL = 5
MAX_AUTO_KEEP = 20


def _init_db():
    """Create the checkpoints table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'auto',
                created_at TIMESTAMP NOT NULL,
                turn INTEGER NOT NULL DEFAULT 0,
                state TEXT,
                messages TEXT,
                metadata TEXT,
                sm_history TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _list_checkpoints() -> list[dict]:
    """List all saved checkpoints sorted by creation time (newest first).

    Backward-compat module-level function — delegates to SQLite.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            """SELECT name, type, created_at, turn,
                      LENGTH(COALESCE(messages,'')) + LENGTH(COALESCE(metadata,'')) AS size
               FROM checkpoints
               ORDER BY created_at DESC"""
        )
        return [
            {
                "name": r[0],
                "type": r[1],
                "created_at": r[2],
                "turn": r[3],
                "size": r[4],
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def _checkpoint_path(name: str) -> str:
    """Backward-compat: returns a placeholder path (no longer file-based)."""
    return str(DB_PATH)


class CheckpointManager:
    """Manages agent state checkpoints — backed by SQLite.

    Usage:
        cm = CheckpointManager()
        await cm.save(state_data, name="my_snapshot", cp_type="manual")
        data = await cm.load("my_snapshot")
        latest = await cm.load_latest()
    """

    def __init__(self, auto_interval: int = AUTO_CHECKPOINT_INTERVAL):
        _init_db()
        self.auto_interval = auto_interval
        self._last_auto_turn = 0
        self._current_turn = 0
        self._migrate_from_json()

    # ── JSON → SQLite migration ────────────────────────────────

    def _migrate_from_json(self):
        """One-time migration: import any JSON checkpoints left on disk."""
        json_dir = DEFAULT_DATA_DIR / "checkpoints"
        if not json_dir.exists():
            return

        conn = self._connect()
        try:
            count = 0
            for f in sorted(json_dir.iterdir()):
                if f.suffix != ".json":
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    name = data.get("name", f.stem)
                    conn.execute(
                        """INSERT OR IGNORE INTO checkpoints
                           (name, type, created_at, turn, state, messages, metadata, sm_history)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            name,
                            data.get("type", "auto"),
                            data.get("created_at", datetime.now(timezone.utc).isoformat()),
                            data.get("turn", 0),
                            json.dumps(data.get("state", ""), ensure_ascii=False),
                            json.dumps(data.get("messages", []), ensure_ascii=False),
                            json.dumps(data.get("metadata", {}), ensure_ascii=False),
                            json.dumps(data.get("sm_history", []), ensure_ascii=False),
                        ),
                    )
                    count += 1
                except (json.JSONDecodeError, OSError, KeyError):
                    pass

            if count:
                conn.commit()
                log.info(f"Migrated {count} checkpoint(s) from JSON to SQLite")

            # Archive old JSON dir (rename to .bak)
            archived = DEFAULT_DATA_DIR / "checkpoints.json.bak"
            json_dir.rename(archived)
            log.info(f"Archived old checkpoints/ directory to {archived}")
        finally:
            conn.close()

    # ── Internal helpers ───────────────────────────────────────

    @staticmethod
    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        return {
            "type": row["type"],
            "name": row["name"],
            "created_at": row["created_at"],
            "turn": row["turn"],
            "state": json.loads(row["state"]) if row["state"] else "",
            "messages": json.loads(row["messages"]) if row["messages"] else [],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "sm_history": json.loads(row["sm_history"]) if row["sm_history"] else [],
        }

    # ── Public API ─────────────────────────────────────────────

    @property
    def should_checkpoint(self) -> bool:
        """Check if an auto-checkpoint should be taken based on turn count."""
        if self._current_turn == 0:
            return False
        return (self._current_turn - self._last_auto_turn) >= self.auto_interval

    async def save(
        self,
        state_data: dict[str, Any],
        name: Optional[str] = None,
        cp_type: str = "auto",
    ) -> str:
        """Save a checkpoint to SQLite.

        Args:
            state_data: Full state dict to snapshot.
            name: Checkpoint name (auto-generated if None).
            cp_type: 'auto' for automatic, 'manual' for user-requested snapshots.

        Returns:
            Checkpoint name.
        """
        if name is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            name = f"checkpoint_{timestamp}"

        now = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (name, type, created_at, turn, state, messages, metadata, sm_history)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    cp_type,
                    now,
                    state_data.get("turn", 0),
                    json.dumps(state_data.get("state", ""), ensure_ascii=False),
                    json.dumps(state_data.get("messages", []), ensure_ascii=False),
                    json.dumps(state_data.get("metadata", {}), ensure_ascii=False),
                    json.dumps(state_data.get("sm_history", []), ensure_ascii=False),
                ),
            )
            conn.commit()

            if cp_type == "auto":
                self._last_auto_turn = self._current_turn

            log.info(f"Checkpoint saved [{cp_type}]: {name}")

            # Prune old auto-checkpoints
            self._prune_old(max_keep=MAX_AUTO_KEEP)

        except sqlite3.Error as e:
            log.error(f"Checkpoint save failed [{name}]: {e}")
            raise
        finally:
            conn.close()

        return name

    async def load(self, name: str) -> Optional[dict[str, Any]]:
        """Load a checkpoint by name.

        Args:
            name: Checkpoint name.

        Returns:
            Checkpoint data dict or None if not found.
        """
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT * FROM checkpoints WHERE name = ?", (name,)
            )
            row = cur.fetchone()
            if row is None:
                log.warning(f"Checkpoint not found: {name}")
                return None
            data = self._row_to_dict(row)
            log.info(f"Checkpoint loaded: {name} (turn={data['turn']})")
            return data
        except sqlite3.Error as e:
            log.error(f"Checkpoint load failed [{name}]: {e}")
            return None
        finally:
            conn.close()

    async def load_latest(self, cp_type: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Load the most recent checkpoint, optionally filtered by type.

        Args:
            cp_type: Filter by 'auto', 'manual', or None for any.

        Returns:
            Latest checkpoint data or None.
        """
        conn = self._connect()
        try:
            if cp_type:
                cur = conn.execute(
                    """SELECT * FROM checkpoints
                       WHERE type = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (cp_type,),
                )
            else:
                cur = conn.execute(
                    """SELECT * FROM checkpoints
                       ORDER BY created_at DESC LIMIT 1"""
                )
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)
        except sqlite3.Error as e:
            log.error(f"Checkpoint load_latest failed: {e}")
            return None
        finally:
            conn.close()

    async def delete(self, name: str) -> bool:
        """Delete a checkpoint by name."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE name = ?", (name,)
            )
            conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                log.info(f"Checkpoint deleted: {name}")
            return deleted
        except sqlite3.Error as e:
            log.error(f"Checkpoint delete failed [{name}]: {e}")
            return False
        finally:
            conn.close()

    async def list(self, cp_type: Optional[str] = None) -> list[dict]:
        """List all checkpoints, optionally filtered by type."""
        conn = self._connect()
        try:
            if cp_type:
                cur = conn.execute(
                    """SELECT name, type, created_at, turn,
                              LENGTH(COALESCE(messages,'')) + LENGTH(COALESCE(metadata,'')) AS size
                       FROM checkpoints
                       WHERE type = ?
                       ORDER BY created_at DESC""",
                    (cp_type,),
                )
            else:
                cur = conn.execute(
                    """SELECT name, type, created_at, turn,
                              LENGTH(COALESCE(messages,'')) + LENGTH(COALESCE(metadata,'')) AS size
                       FROM checkpoints
                       ORDER BY created_at DESC"""
                )
            return [
                {
                    "name": r[0],
                    "type": r[1],
                    "created_at": r[2],
                    "turn": r[3],
                    "size": r[4],
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def _prune_old(self, max_keep: int = MAX_AUTO_KEEP):
        """Remove oldest auto-checkpoints beyond max_keep."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """SELECT name FROM checkpoints
                   WHERE type = 'auto'
                   ORDER BY created_at DESC"""
            )
            rows = cur.fetchall()
            if len(rows) <= max_keep:
                return
            to_remove = [r[0] for r in rows[max_keep:]]
            for name in to_remove:
                conn.execute("DELETE FROM checkpoints WHERE name = ?", (name,))
                log.debug(f"Pruned old checkpoint: {name}")
            conn.commit()
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    def update_turn(self, turn: int):
        """Update internal turn counter (called from agent loop)."""
        self._current_turn = turn

    def reset(self):
        """Reset checkpoint tracking state."""
        self._last_auto_turn = 0
        self._current_turn = 0


# Singleton
checkpoint_manager = CheckpointManager()
