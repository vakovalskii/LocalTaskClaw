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
            full_msg TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        -- Add full_msg column to existing DBs (idempotent)
        CREATE TABLE IF NOT EXISTS _dummy_migration (id INTEGER);

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

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#f59e0b',
            emoji TEXT NOT NULL DEFAULT '🤖',
            system_prompt TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kanban_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
            column TEXT NOT NULL DEFAULT 'backlog',
            position INTEGER NOT NULL DEFAULT 0,
            artifact TEXT,
            status TEXT NOT NULL DEFAULT 'idle',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_kanban_column ON kanban_tasks(column);
    """)
    conn.commit()
    # Migrations: add columns added after initial schema
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN full_msg TEXT")
        conn.commit()
        core_logger.info("DB migration: added full_msg column")
    except Exception:
        pass  # Column already exists
    conn.close()
    core_logger.info(f"DB initialized: {CONFIG.db_path}")


def save_messages(session_key: str, messages: list):
    """Persist full conversation history (role + content + tool_calls + tool_call_id)."""
    conn = get_db()
    try:
        # Ensure full_msg column exists (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN full_msg TEXT")
            conn.commit()
        except Exception:
            pass  # Column already exists

        conn.execute("DELETE FROM messages WHERE session_key = ?", (session_key,))
        rows = []
        for m in messages:
            role = m["role"]
            content = m.get("content") or ""
            if isinstance(content, list):
                content = json.dumps(content)
            full_msg = json.dumps(m, ensure_ascii=False)
            rows.append((session_key, role, content, full_msg))

        conn.executemany(
            "INSERT INTO messages (session_key, role, content, full_msg) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE session_key = ?",
            (session_key,),
        )
        conn.commit()
    finally:
        conn.close()


def load_messages(session_key: str) -> list:
    """Load full conversation history including tool_calls and tool_call_id."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT role, content, full_msg FROM messages WHERE session_key = ? ORDER BY id",
            (session_key,),
        ).fetchall()
        result = []
        for row in rows:
            # Prefer full_msg (complete message dict), fall back to role+content
            if row["full_msg"]:
                try:
                    msg = json.loads(row["full_msg"])
                    result.append(msg)
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            # Legacy fallback: reconstruct from role+content
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


# ── Agents (kanban identities) ────────────────────────────────────────────────

def get_agents() -> list:
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM agents ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()


def create_agent(name: str, color: str, emoji: str, system_prompt: str) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO agents (name, color, emoji, system_prompt) VALUES (?, ?, ?, ?)",
            (name, color, emoji, system_prompt),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_agent(agent_id: int, **fields) -> dict | None:
    allowed = {"name", "color", "emoji", "system_prompt"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return None
    conn = get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE agents SET {sets} WHERE id = ?", (*updates.values(), agent_id))
        conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_agent(agent_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()
    finally:
        conn.close()


# ── Kanban tasks ──────────────────────────────────────────────────────────────

def get_kanban_tasks() -> list:
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT kt.*, a.name as agent_name, a.color as agent_color, a.emoji as agent_emoji
            FROM kanban_tasks kt
            LEFT JOIN agents a ON kt.agent_id = a.id
            ORDER BY kt.column, kt.position, kt.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_kanban_task(title: str, description: str, agent_id: int | None, column: str = "backlog") -> dict:
    conn = get_db()
    try:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM kanban_tasks WHERE column = ?", (column,)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO kanban_tasks (title, description, agent_id, column, position) VALUES (?, ?, ?, ?, ?)",
            (title, description, agent_id, column, pos),
        )
        conn.commit()
        row = conn.execute("""
            SELECT kt.*, a.name as agent_name, a.color as agent_color, a.emoji as agent_emoji
            FROM kanban_tasks kt LEFT JOIN agents a ON kt.agent_id = a.id
            WHERE kt.id = ?
        """, (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_kanban_task(task_id: int, **fields) -> dict | None:
    allowed = {"title", "description", "agent_id", "column", "position", "artifact", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None
    conn = get_db()
    try:
        updates["updated_at"] = "datetime('now')"
        # updated_at is a SQL expression, handle separately
        reg = {k: v for k, v in updates.items() if k != "updated_at"}
        sets = ", ".join(f"{k} = ?" for k in reg) + ", updated_at = datetime('now')"
        conn.execute(f"UPDATE kanban_tasks SET {sets} WHERE id = ?", (*reg.values(), task_id))
        conn.commit()
        row = conn.execute("""
            SELECT kt.*, a.name as agent_name, a.color as agent_color, a.emoji as agent_emoji
            FROM kanban_tasks kt LEFT JOIN agents a ON kt.agent_id = a.id
            WHERE kt.id = ?
        """, (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_kanban_task(task_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM kanban_tasks WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()
