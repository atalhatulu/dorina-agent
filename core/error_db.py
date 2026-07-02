"""
Error logging database — stores tool/LLM errors for analysis.
Simple SQLite-based logger. Falls back to log.error if DB unavailable.
"""

from __future__ import annotations
from pathlib import Path
from core.constants import DORINA_HOME
from datetime import datetime, timezone
import traceback

try:
    import sqlite3
    _DB_PATH = DORINA_HOME / "data" / "error_log.db"
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(_DB_PATH))
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            source TEXT,
            error_type TEXT,
            error_msg TEXT,
            traceback TEXT,
            context TEXT
        )
    """)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS error_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_key TEXT UNIQUE,
            count INTEGER DEFAULT 1,
            first_seen TEXT,
            last_seen TEXT,
            last_error_msg TEXT,
            last_source TEXT
        )
    """)
    _conn.commit()
    _db_ok = True
except (sqlite3.Error, OSError):
    _db_ok = False

from core.logger import log


def _log(source: str, error_type: str, error_msg: str, context: str = ""):
    """Log error to DB (if available) and always to log.error."""
    log.error("[%s] %s: %s", source, error_type, error_msg[:200])
    if not _db_ok:
        return
    try:
        _conn.execute(
            "INSERT INTO error_log (timestamp, source, error_type, error_msg, traceback, context) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), source, error_type, str(error_msg)[:500],
             traceback.format_exc()[:2000], str(context)[:500])
        )
        _conn.commit()
    except sqlite3.Error:
        pass


def log_tool_error(tool_name: str, error: Exception | None = None,
                   tool_call_id: str = "", message: str = "", traceback: str = ""):
    _log(f"tool:{tool_name}", type(error).__name__ if error else "Error",
         message or str(error) if error else message,
         f"call_id={tool_call_id} tb={traceback[:100]}" if traceback else f"call_id={tool_call_id}")


def log_llm_error(provider: str, model: str, error: Exception, prompt_tokens: int = 0):
    _log(f"llm:{provider}/{model}", type(error).__name__, str(error), f"tokens={prompt_tokens}")


def log_system_error(component: str, error: Exception):
    _log(f"system:{component}", type(error).__name__, str(error))


# ── Error Pattern Tracking ──────────────────────────────────

def _make_pattern_key(source: str, error_type: str) -> str:
    """Normalize a (source, error_type) pair into a pattern key."""
    return f"{source}|{error_type}"


def log_error_pattern(source: str, error_type: str, error_msg: str = "") -> str:
    """Record an error pattern occurrence. Returns the pattern key."""
    pattern_key = _make_pattern_key(source, error_type)
    if not _db_ok:
        return pattern_key

    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = _conn.execute(
            "SELECT id, count FROM error_patterns WHERE pattern_key = ?",
            (pattern_key,),
        )
        row = cursor.fetchone()
        if row:
            _conn.execute(
                "UPDATE error_patterns SET count = count + 1, last_seen = ?, last_error_msg = ?, last_source = ? WHERE pattern_key = ?",
                (now, str(error_msg)[:300], str(source)[:100], pattern_key),
            )
        else:
            _conn.execute(
                "INSERT INTO error_patterns (pattern_key, count, first_seen, last_seen, last_error_msg, last_source) VALUES (?, 1, ?, ?, ?, ?)",
                (pattern_key, now, now, str(error_msg)[:300], str(source)[:100]),
            )
        _conn.commit()
    except sqlite3.Error:
        pass

    return pattern_key


def get_frequent_patterns(min_count: int = 3) -> list[dict]:
    """Return error patterns that have occurred at least `min_count` times.

    Results are ordered by count descending. Used by self-reflection
    in experimental_loop to detect recurring failures.
    """
    if not _db_ok:
        return []

    try:
        cursor = _conn.execute(
            "SELECT pattern_key, count, first_seen, last_seen, last_error_msg, last_source "
            "FROM error_patterns WHERE count >= ? ORDER BY count DESC LIMIT 20",
            (min_count,),
        )
        return [
            {
                "pattern_key": row[0],
                "count": row[1],
                "first_seen": row[2],
                "last_seen": row[3],
                "last_error_msg": row[4],
                "last_source": row[5],
            }
            for row in cursor.fetchall()
        ]
    except sqlite3.Error:
        return []


def clear_error_patterns() -> int:
    """Reset all error pattern counters. Returns number of rows deleted."""
    if not _db_ok:
        return 0
    try:
        cursor = _conn.execute("DELETE FROM error_patterns")
        _conn.commit()
        return cursor.rowcount
    except sqlite3.Error:
        return 0
