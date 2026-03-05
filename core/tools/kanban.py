"""Kanban tools — full agent workflow: list, run, verify, report."""

import os
import json
from models import ToolResult, ToolContext
from db import (
    get_kanban_tasks, update_kanban_task, get_agents,
    create_kanban_task,
)

VALID_COLS = {"backlog", "in_progress", "review", "done", "needs_human"}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "kanban_list",
            "description": (
                "List all kanban tasks with their current column, status, and assigned agent. "
                "Also shows available agents with their IDs and roles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {
                        "type": "string",
                        "description": "Filter by column: backlog, in_progress, review, done, needs_human. Omit for all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_run",
            "description": (
                "Start the assigned agent on a kanban task. "
                "Automatically moves the task to in_progress. "
                "Non-blocking — agent runs in background. "
                "Use kanban_list to check status afterwards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID to run"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_read_result",
            "description": (
                "Read the artifact (result) produced by a worker agent after task completion. "
                "Use this to verify quality of work before approving or requesting retry."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID to read result for"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_verify",
            "description": (
                "Approve or reject a completed task after reviewing its result. "
                "approved=true → marks status='verified', stays in review (human moves to done). "
                "approved=false → moves back to 'backlog' for retry (or 'needs_human' if retry_count exceeded). "
                "Always provide a comment explaining your decision."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID to verify"},
                    "approved": {"type": "boolean", "description": "True to approve, False to reject and retry"},
                    "comment": {"type": "string", "description": "Verification feedback — required"},
                },
                "required": ["task_id", "approved", "comment"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_report",
            "description": (
                "Send a structured orchestration report via Telegram. "
                "Call this at the end of each orchestration cycle with a summary of all tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Overall cycle summary (1-2 sentences)",
                    },
                    "results": {
                        "type": "array",
                        "description": "Per-task results",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task_id":  {"type": "integer"},
                                "title":    {"type": "string"},
                                "status":   {"type": "string", "description": "done / failed / needs_human / skipped"},
                                "comment":  {"type": "string", "description": "Brief result note"},
                            },
                            "required": ["task_id", "title", "status"],
                        },
                    },
                },
                "required": ["summary", "results"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_move",
            "description": (
                "Move a task to a different column manually. "
                "Prefer kanban_run to start agents and kanban_verify to approve/reject. "
                "Columns: backlog, in_progress, review, done, needs_human."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "column":  {"type": "string"},
                },
                "required": ["task_id", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_update",
            "description": "Update a task's title, description, or assigned agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id":     {"type": "integer"},
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "agent_id":    {"type": "integer"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_create",
            "description": "Create a new kanban task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "agent_id":    {"type": "integer"},
                    "column":      {"type": "string", "description": "backlog (default)"},
                    "board_id":    {"type": "integer", "description": "kanban board id (default 1)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kanban_create_agent",
            "description": (
                "Create a new agent (worker or orchestrator) in the system. "
                "Use this when spawning a new specialist for a project. "
                "Returns the new agent's id — use it with kanban_create to assign tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":          {"type": "string", "description": "Agent display name"},
                    "emoji":         {"type": "string", "description": "Single emoji for agent avatar"},
                    "color":         {"type": "string", "description": "Hex color, e.g. #3b82f6"},
                    "role":          {"type": "string", "description": "worker or orchestrator"},
                    "system_prompt": {"type": "string", "description": "Full system prompt for this agent"},
                },
                "required": ["name", "system_prompt"],
            },
        },
    },
]


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_tasks(tasks: list, column_filter: str | None = None) -> str:
    if column_filter:
        tasks = [t for t in tasks if t["column"] == column_filter]
    if not tasks:
        return "No tasks found."

    col_order = ["backlog", "in_progress", "review", "needs_human", "done"]
    cols: dict[str, list] = {}
    for t in tasks:
        cols.setdefault(t["column"], []).append(t)

    lines = []
    for col in col_order:
        if col not in cols:
            continue
        lines.append(f"\n[{col.upper()}]")
        for t in cols[col]:
            agent = f" → {t['agent_emoji']} {t['agent_name']}" if t.get("agent_name") else " → (no agent)"
            status = f" [{t['status']}]" if t["status"] not in ("idle", "done") else ""
            retry = f" retry#{t.get('retry_count',0)}" if t.get("retry_count", 0) > 0 else ""
            has_result = " [has result]" if t.get("artifact") else ""
            lines.append(f"  #{t['id']} {t['title']}{agent}{status}{retry}{has_result}")
            if t.get("description"):
                lines.append(f"      {t['description'][:120]}")
    return "\n".join(lines)


# ── Tool handlers ─────────────────────────────────────────────────────────────

async def tool_kanban_list(args: dict, ctx: ToolContext) -> ToolResult:
    column = args.get("column")
    tasks = get_kanban_tasks()
    agents = get_agents()

    summary = _fmt_tasks(tasks, column)

    agent_lines = "\n\nAVAILABLE AGENTS:"
    for a in agents:
        agent_lines += f"\n  #{a['id']} {a['emoji']} {a['name']} [{a.get('role','worker')}]"
    summary += agent_lines

    return ToolResult(True, output=summary)


async def tool_kanban_run(args: dict, ctx: ToolContext) -> ToolResult:
    from config import CONFIG
    import httpx

    task_id = args.get("task_id")
    tasks = get_kanban_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return ToolResult(False, error=f"Task #{task_id} not found")
    if not task.get("agent_id"):
        return ToolResult(False, error=f"Task #{task_id} has no agent assigned")
    if task["status"] == "running":
        return ToolResult(False, error=f"Task #{task_id} is already running")

    try:
        url = f"http://localhost:{CONFIG.api_port}/kanban/tasks/{task_id}/run"
        headers = {"X-Api-Key": CONFIG.api_secret} if CONFIG.api_secret else {}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 200:
                return ToolResult(True, output=f"Agent started on task #{task_id} '{task['title']}'")
            return ToolResult(False, error=f"Failed to start agent: {resp.text[:200]}")
    except Exception as e:
        return ToolResult(False, error=f"Request failed: {e}")


async def tool_kanban_read_result(args: dict, ctx: ToolContext) -> ToolResult:
    task_id = args.get("task_id")
    tasks = get_kanban_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return ToolResult(False, error=f"Task #{task_id} not found")

    artifact_path = task.get("artifact")
    if not artifact_path:
        return ToolResult(False, error=f"Task #{task_id} has no result yet (artifact not set)")

    if not os.path.exists(artifact_path):
        return ToolResult(False, error=f"Artifact file not found: {artifact_path}")

    try:
        with open(artifact_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Truncate very long artifacts for context efficiency
        if len(content) > 6000:
            content = content[:6000] + f"\n\n... [truncated, total {len(content)} chars]"
        return ToolResult(True, output=f"=== Result for task #{task_id}: {task['title']} ===\n\n{content}")
    except Exception as e:
        return ToolResult(False, error=f"Failed to read artifact: {e}")


async def tool_kanban_verify(args: dict, ctx: ToolContext) -> ToolResult:
    task_id = args.get("task_id")
    approved = args.get("approved")
    comment = args.get("comment", "").strip()

    if not comment:
        return ToolResult(False, error="comment is required for verification")

    tasks = get_kanban_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return ToolResult(False, error=f"Task #{task_id} not found")

    if approved:
        # Approved → stays in review, status=verified. Only a human can move to done.
        update_kanban_task(task_id, column="review", status="verified")
        return ToolResult(True, output=f"✅ Task #{task_id} '{task['title']}' APPROVED → review (awaiting human sign-off)\nComment: {comment}")
    else:
        retry_count = (task.get("retry_count") or 0) + 1
        max_retries = 2
        if retry_count > max_retries:
            update_kanban_task(task_id, column="needs_human", status="idle")
            return ToolResult(True, output=(
                f"❌ Task #{task_id} '{task['title']}' REJECTED after {retry_count} retries → needs_human\n"
                f"Comment: {comment}"
            ))
        else:
            # Reset for retry — clear artifact so worker starts fresh
            update_kanban_task(task_id, column="backlog", status="idle", artifact=None)
            return ToolResult(True, output=(
                f"🔄 Task #{task_id} '{task['title']}' REJECTED → backlog for retry #{retry_count}\n"
                f"Comment: {comment}"
            ))


async def tool_kanban_report(args: dict, ctx: ToolContext) -> ToolResult:
    from config import CONFIG
    import httpx

    summary = args.get("summary", "")
    results = args.get("results", [])

    if not CONFIG.bot_token or not CONFIG.owner_id:
        return ToolResult(False, error="BOT_TOKEN or OWNER_ID not configured")

    # Build formatted Telegram message
    status_icons = {
        "done": "✅", "approved": "✅", "verified": "✅",
        "failed": "❌", "error": "❌", "needs_human": "🙋",
        "skipped": "⏭", "running": "⏳", "started": "🚀",
    }
    lines = [f"📋 *Отчёт оркестратора*\n\n{summary}\n"]
    for r in results:
        status = r.get("status", "").lower()
        icon = status_icons.get(status, "•")
        comment = f" — {r['comment']}" if r.get("comment") else ""
        lines.append(f"{icon} #{r.get('task_id', '?')} {r.get('title', '?')}{comment}")

    started_count = sum(1 for r in results if r.get("status", "").lower() in ("started", "running"))
    done_count    = sum(1 for r in results if r.get("status", "").lower() in ("done", "approved", "verified"))
    failed_count  = sum(1 for r in results if r.get("status", "").lower() in ("failed", "error", "needs_human"))
    skip_count    = sum(1 for r in results if r.get("status", "").lower() == "skipped")

    parts = []
    if started_count: parts.append(f"{started_count} запущено")
    if done_count: parts.append(f"{done_count} выполнено")
    if failed_count: parts.append(f"{failed_count} с ошибкой")
    if skip_count: parts.append(f"{skip_count} пропущено")
    if not parts: parts.append(f"{len(results)} обработано")
    lines.append(f"\n*Итого:* {', '.join(parts)}")

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{CONFIG.bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "chat_id": CONFIG.owner_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            if resp.status_code != 200:
                # Retry plain text
                await client.post(url, json={"chat_id": CONFIG.owner_id, "text": text})
        return ToolResult(True, output=f"Report sent: {done_count} done, {failed_count} failed, {skip_count} skipped")
    except Exception as e:
        return ToolResult(False, error=f"Report send failed: {e}")


async def tool_kanban_move(args: dict, ctx: ToolContext) -> ToolResult:
    task_id = args.get("task_id")
    column = args.get("column", "").strip()
    if column not in VALID_COLS:
        return ToolResult(False, error=f"Invalid column '{column}'. Valid: {', '.join(VALID_COLS)}")
    task = update_kanban_task(task_id, column=column)
    if not task:
        return ToolResult(False, error=f"Task #{task_id} not found")
    return ToolResult(True, output=f"Task #{task_id} '{task['title']}' moved to {column}")


async def tool_kanban_update(args: dict, ctx: ToolContext) -> ToolResult:
    task_id = args.get("task_id")
    fields = {k: v for k, v in args.items() if k != "task_id" and v is not None}
    if not fields:
        return ToolResult(False, error="No fields to update")
    task = update_kanban_task(task_id, **fields)
    if not task:
        return ToolResult(False, error=f"Task #{task_id} not found")
    return ToolResult(True, output=f"Task #{task_id} updated: {task['title']}")


async def tool_kanban_create(args: dict, ctx: ToolContext) -> ToolResult:
    title = args.get("title", "").strip()
    if not title:
        return ToolResult(False, error="title is required")
    description = args.get("description", "")
    agent_id = args.get("agent_id")
    column = args.get("column", "backlog")
    board_id = args.get("board_id", 1)
    if column not in VALID_COLS:
        column = "backlog"
    task = create_kanban_task(title, description, agent_id, column, board_id=board_id)
    return ToolResult(True, output=f"Task #{task['id']} created: '{title}' in {column} (board #{board_id})")


async def tool_kanban_create_agent(args: dict, ctx: ToolContext) -> ToolResult:
    from db import create_agent, get_agents
    name = args.get("name", "").strip()
    if not name:
        return ToolResult(False, error="name is required")
    system_prompt = args.get("system_prompt", "").strip()
    if not system_prompt:
        return ToolResult(False, error="system_prompt is required")
    emoji = args.get("emoji", "🤖")
    color = args.get("color", "#6366f1")
    role = args.get("role", "worker")
    if role not in ("worker", "orchestrator"):
        role = "worker"

    agents = get_agents()
    if len(agents) >= 10:
        return ToolResult(False, error="Maximum 10 agents reached. Delete unused agents first.")

    agent = create_agent(name, color, emoji, system_prompt, role)
    return ToolResult(
        True,
        output=(
            f"Agent #{agent['id']} created: {emoji} {name} [{role}]\n"
            f"Use agent_id={agent['id']} when calling kanban_create to assign tasks."
        ),
    )
