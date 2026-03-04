"""SQLite storage — sessions, scheduled tasks."""

import sqlite3
import json
import os
from datetime import datetime
from config import CONFIG
from logger import core_logger


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CONFIG.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(CONFIG.db_path), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_key);

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cron TEXT,
            interval_minutes INTEGER,
            prompt TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_events_session ON agent_events(session_key);
    """)
    conn.commit()
    conn.close()
    core_logger.info(f"DB initialized: {CONFIG.db_path}")


def save_messages(session_key: str, messages: list):
    """Persist conversation history for a session."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM messages WHERE session_key = ?", (session_key,)
        )
        conn.executemany(
            "INSERT INTO messages (session_key, role, content) VALUES (?, ?, ?)",
            [(session_key, m["role"], json.dumps(m["content"]) if isinstance(m["content"], list) else m["content"])
             for m in messages],
        )
        conn.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE session_key = ? ",
            (session_key,),
        )
        conn.commit()
    finally:
        conn.close()


def load_messages(session_key: str) -> list:
    """Load conversation history for a session."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_key = ? ORDER BY id",
            (session_key,),
        ).fetchall()
        result = []
        for row in rows:
            content = row["content"]
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass
            result.append({"role": row["role"], "content": content})
        return result
    finally:
        conn.close()


def ensure_session(session_key: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM sessions WHERE session_key = ?", (session_key,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO sessions (session_key) VALUES (?)", (session_key,)
            )
            conn.commit()
    finally:
        conn.close()


def log_event(session_key: str, event_type: str, data: dict):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO agent_events (session_key, event_type, data) VALUES (?, ?, ?)",
            (session_key, event_type, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def get_scheduled_tasks() -> list:
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM scheduled_tasks WHERE enabled = 1 ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()


def update_task_last_run(task_id: int, next_run: str):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE scheduled_tasks SET last_run = datetime('now'), next_run = ? WHERE id = ?",
            (next_run, task_id),
        )
        conn.commit()
    finally:
        conn.close()
