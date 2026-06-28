"""Epizodik bellek - oturum geçmişini SQLite'da sakla."""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = Path("data/episodic.db")


class EpisodicMemory:
    """Geçmiş oturumları saklar."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH))
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                messages TEXT,
                summary TEXT
            )
        """)
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

    def save_session(self, session_id: str, title: str, messages: list[dict], summary: str = ""):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions 
               (id, title, created_at, updated_at, messages, summary)
               VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE id=?), ?), ?, ?, ?)""",
            (session_id, title, session_id, now, now, json.dumps(messages, ensure_ascii=False), summary)
        )
        self.conn.commit()

    def load_session(self, session_id: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "messages": json.loads(row[4]),
                "summary": row[5],
            }
        return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        )
        return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in cur.fetchall()]

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

    def delete_session(self, session_id: str):
        self.conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.conn.commit()
