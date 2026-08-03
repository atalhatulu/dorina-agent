"""Episodic memory — store reflection/lesson memories in SQLite."""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from core.constants import DEFAULT_DATA_DIR
from memory.base import BaseMemory

DB_PATH = DEFAULT_DATA_DIR / "episodic.db"


class EpisodicMemory(BaseMemory):
    """Stores past lessons (reflexion) and key-value memories."""

    memory_type = "episodic"

    def __init__(self):
        super().__init__()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH))
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                content TEXT,
                category TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        self.conn.commit()

    # ── BaseMemory compatibility methods ────────────────────────

    def add(self, key: str, content: str, metadata: Optional[dict] = None) -> None:
        """BaseMemory compatible: add a key-value pair."""
        category = (metadata or {}).get("category", "general")
        self.save_memory(key, content, category=category)

    def get(self, key: str) -> Any:
        """BaseMemory compatible: get a value by key."""
        return self.get_memory(key)

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """BaseMemory compatible: search content."""
        results = self.search_memories(query)
        return results[:n_results]

    def delete(self, key: str) -> bool:
        """BaseMemory compatible: delete memory by key."""
        cur = self.conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0

    def clear(self):
        """BaseMemory compatible: clear all memories."""
        self.conn.execute("DELETE FROM memories")
        self.conn.commit()

    def count(self) -> int:
        """BaseMemory compatible: memory count."""
        cur = self.conn.execute("SELECT COUNT(*) FROM memories")
        return cur.fetchone()[0]

    # ── Core API ────────────────────────────────────────────────

    def save_memory(self, key: str, content: str, category: str = "general"):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO memories (key, content, category, created_at, updated_at)
               VALUES (?, ?, ?, COALESCE((SELECT created_at FROM memories WHERE key=?), ?), ?)""",
            (key, content, category, key, now, now)
        )
        self.conn.commit()

    def get_memory(self, key: str) -> Optional[str]:
        cur = self.conn.execute("SELECT content FROM memories WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def search_memories(self, query: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT key, content, category FROM memories WHERE content LIKE ?",
            (f"%{query}%",)
        )
        return [{"key": r[0], "content": r[1], "category": r[2]} for r in cur.fetchall()]
