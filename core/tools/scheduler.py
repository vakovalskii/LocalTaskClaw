"""Scheduler tool — create, list, delete scheduled tasks (stored in SQLite)."""

import sqlite3
from db import get_db
from logger import tool_logger
from models import ToolResult, ToolContext


async def tool_schedule(args: dict, ctx: ToolContext) -> ToolResult:
    action = args.get("action", "list")

    if action == "list":
        conn = get_db()
        rows = conn.execute("SELECT id, name, cron, interval_minutes, prompt, enabled, last_run, next_run FROM scheduled_tasks ORDER BY id").fetchall()
        conn.close()
        if not rows:
            return ToolResult(True, output="No scheduled tasks")
        lines = []
        for r in rows:
            status = "✓" if r["enabled"] else "✗"
            schedule = r["cron"] or f"every {r['interval_minutes']}min"
            lines.append(f"[{r['id']}] {status} {r['name']} — {schedule}\n  Last: {r['last_run'] or 'never'}, Next: {r['next_run'] or 'unknown'}\n  Prompt: {r['prompt'][:80]}")
        return ToolResult(True, output="\n\n".join(lines))

    elif action == "create":
        name = args.get("name", "")
        prompt = args.get("prompt", "")
        interval = args.get("interval_minutes")
        cron = args.get("cron")

        if not name or not prompt:
            return ToolResult(False, error="name and prompt are required")
        if not interval and not cron:
            return ToolResult(False, error="interval_minutes or cron is required")

        conn = get_db()
        conn.execute(
            "INSERT INTO scheduled_tasks (name, cron, interval_minutes, prompt) VALUES (?, ?, ?, ?)",
            (name, cron, interval, prompt),
        )
        conn.commit()
        conn.close()
        return ToolResult(True, output=f"Task '{name}' created")

    elif action == "delete":
        task_id = args.get("id")
        if not task_id:
            return ToolResult(False, error="id is required")
        conn = get_db()
        conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        return ToolResult(True, output=f"Task {task_id} deleted")

    elif action == "toggle":
        task_id = args.get("id")
        if not task_id:
            return ToolResult(False, error="id is required")
        conn = get_db()
        row = conn.execute("SELECT enabled FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            conn.close()
            return ToolResult(False, error=f"Task {task_id} not found")
        new_state = 0 if row["enabled"] else 1
        conn.execute("UPDATE scheduled_tasks SET enabled = ? WHERE id = ?", (new_state, task_id))
        conn.commit()
        conn.close()
        return ToolResult(True, output=f"Task {task_id} {'enabled' if new_state else 'disabled'}")

    else:
        return ToolResult(False, error=f"Unknown action: {action}. Use list/create/delete/toggle")


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "schedule_task",
        "description": "Manage scheduled tasks — recurring prompts that run automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "delete", "toggle"],
                    "description": "list — show tasks, create — add new, delete — remove, toggle — enable/disable",
                },
                "name": {"type": "string", "description": "Task name (for create)"},
                "prompt": {"type": "string", "description": "What the agent should do when triggered"},
                "interval_minutes": {"type": "integer", "description": "Run every N minutes"},
                "cron": {"type": "string", "description": "Cron expression (e.g. '0 9 * * *' for 9am daily)"},
                "id": {"type": "integer", "description": "Task ID (for delete/toggle)"},
            },
            "required": ["action"],
        },
    },
}
