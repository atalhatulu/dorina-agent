"""Hata kayıt veritabanı — SQLite tabanlı.

Tool hataları, LLM hataları ve diğer hataları yapılandırılmış şekilde
kaydeder. Sorgulanabilir, zaman damgalı, session ID'li.
"""
from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".dorina" / "data" / "error_log.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_local = threading.local()


def _get_db() -> sqlite3.Connection:
    """Thread-safe connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _init_db(_local.conn)
    return _local.conn


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS error_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            session_id  TEXT,
            error_type  TEXT NOT NULL,      -- 'tool' | 'llm' | 'system'
            category    TEXT,               -- FailoverReason değeri
            tool_name   TEXT,
            provider    TEXT,
            model       TEXT,
            message     TEXT,
            traceback   TEXT,
            context     TEXT                -- JSON
        );
        CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON error_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_errors_session ON error_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_errors_type ON error_log(error_type);
    """)


def log_tool_error(
    tool_name: str,
    message: str,
    traceback: str = "",
    session_id: str = "",
    context: dict | None = None,
):
    """Log a tool execution error."""
    conn = _get_db()
    conn.execute(
        """INSERT INTO error_log (timestamp, session_id, error_type, tool_name, message, traceback, context)
           VALUES (?, ?, 'tool', ?, ?, ?, ?)""",
        (_now(), session_id, tool_name, message[:1000], traceback[:2000],
         json.dumps(context or {}, ensure_ascii=False)),
    )
    conn.commit()


def log_llm_error(
    message: str,
    category: str = "unknown",
    provider: str = "",
    model: str = "",
    session_id: str = "",
    traceback: str = "",
):
    """Log an LLM API error."""
    conn = _get_db()
    conn.execute(
        """INSERT INTO error_log (timestamp, session_id, error_type, category, provider, model, message, traceback)
           VALUES (?, ?, 'llm', ?, ?, ?, ?, ?)""",
        (_now(), session_id, category, provider, model, message[:1000], traceback[:2000]),
    )
    conn.commit()


def log_system_error(
    message: str,
    session_id: str = "",
    traceback: str = "",
):
    """Log a system-level error."""
    conn = _get_db()
    conn.execute(
        """INSERT INTO error_log (timestamp, session_id, error_type, message, traceback)
           VALUES (?, ?, 'system', ?, ?)""",
        (_now(), session_id, message[:1000], traceback[:2000]),
    )
    conn.commit()


def query_errors(
    error_type: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query error log with filters."""
    conn = _get_db()
    conditions = []
    params = []
    if error_type:
        conditions.append("error_type = ?")
        params.append(error_type)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if tool_name:
        conditions.append("tool_name = ?")
        params.append(tool_name)

    where = " AND ".join(conditions) if conditions else "1=1"
    query = "SELECT * FROM error_log WHERE " + where + " ORDER BY timestamp DESC LIMIT ?"
    rows = conn.execute(query, params + [limit]).fetchall()
    return [dict(r) for r in rows]


def get_error_stats() -> dict:
    """Get error statistics."""
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0]
    by_type = conn.execute(
        "SELECT error_type, COUNT(*) as cnt FROM error_log GROUP BY error_type"
    ).fetchall()
    by_category = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM error_log WHERE category IS NOT NULL GROUP BY category"
    ).fetchall()
    recent = conn.execute(
        "SELECT timestamp, error_type, tool_name, category, message FROM error_log ORDER BY timestamp DESC LIMIT 5"
    ).fetchall()
    return {
        "total": total,
        "by_type": {r["error_type"]: r["cnt"] for r in by_type},
        "by_category": {r["category"]: r["cnt"] for r in by_category},
        "recent": [dict(r) for r in recent],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
