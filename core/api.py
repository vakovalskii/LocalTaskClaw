"""FastAPI app — agent endpoint consumed by bot and admin UI."""

import json
import os
import asyncio
import time
import httpx
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import CONFIG
from logger import core_logger
from agent.run import run_agent
from agent.session import sessions
from db import (
    get_db, get_scheduled_tasks,
    get_agents, create_agent, update_agent, delete_agent,
    get_kanban_tasks, create_kanban_task, update_kanban_task, delete_kanban_task,
)

app = FastAPI(title="LocalTaskClaw Core", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve admin UI at /admin
_admin_dir = os.path.join(os.path.dirname(__file__), "..", "admin")
if os.path.isdir(_admin_dir):
    app.mount("/admin", StaticFiles(directory=_admin_dir, html=True), name="admin")


def _check_auth(x_api_key: str = Header(default="")):
    if CONFIG.api_secret and x_api_key != CONFIG.api_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _safe_path(path: str) -> str:
    """Resolve path, block traversal outside workspace."""
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        resolved = os.path.realpath(os.path.join(CONFIG.workspace, path))
    workspace = os.path.realpath(CONFIG.workspace)
    if not resolved.startswith(workspace):
        raise HTTPException(status_code=403, detail="Path outside workspace")
    return resolved


# ── Models ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    chat_id: int = 0
    stream: bool = False
    source: str = "bot"  # "bot" = came from Telegram bot, "admin" = came from web UI

class ClearRequest(BaseModel):
    chat_id: int = 0

class WriteFileRequest(BaseModel):
    path: str
    content: str

class TaskCreateRequest(BaseModel):
    name: str
    prompt: str
    interval_minutes: int | None = None
    cron: str | None = None

class SettingsRequest(BaseModel):
    model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    brave_api_key: str | None = None
    memory_enabled: bool | None = None
    max_iterations: int | None = None
    command_timeout: int | None = None

class AgentCreateRequest(BaseModel):
    name: str
    color: str = "#f59e0b"
    emoji: str = "🤖"
    system_prompt: str = ""

class AgentUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None
    emoji: str | None = None
    system_prompt: str | None = None

class KanbanTaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    agent_id: int | None = None
    column: str = "backlog"

class KanbanTaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    agent_id: int | None = None
    column: str | None = None
    position: int | None = None

class KanbanTaskMoveRequest(BaseModel):
    column: str
    position: int | None = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "model": CONFIG.model, "workspace": CONFIG.workspace}


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest, _=Depends(_check_auth)):
    chat_id = req.chat_id or CONFIG.owner_id or 0
    forward = (req.source == "admin")  # only forward admin UI messages to Telegram
    if req.stream:
        return StreamingResponse(
            _stream_agent(chat_id, req.message, forward=forward),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    result = await run_agent(chat_id, req.message)
    if forward and CONFIG.bot_token and CONFIG.owner_id:
        asyncio.create_task(_forward_to_telegram(result.text))
    return {
        "text": result.text,
        "tool_events": result.tool_events,
        "tokens": {"prompt": result.total_prompt_tokens, "completion": result.total_completion_tokens},
    }


async def _stream_agent(chat_id: int, message: str, forward: bool = False) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event_type: str, data: dict):
        await queue.put((event_type, data))

    asyncio.create_task(
        _run_and_signal(chat_id, message, on_event, queue, forward=forward)
    )

    while True:
        item = await queue.get()
        if item is None:
            yield "data: [DONE]\n\n"
            break
        event_type, data = item
        yield f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


async def _run_and_signal(chat_id, message, on_event, queue, forward=False):
    try:
        result = await run_agent(chat_id, message, on_event=on_event)
        if forward and CONFIG.bot_token and CONFIG.owner_id:
            asyncio.create_task(_forward_to_telegram(result.text))
    finally:
        await queue.put(None)


async def _forward_to_telegram(text: str):
    """Send agent response to owner via Telegram bot API (fire-and-forget)."""
    if not text or not CONFIG.bot_token or not CONFIG.owner_id:
        return
    url = f"https://api.telegram.org/bot{CONFIG.bot_token}/sendMessage"
    # Split if needed (Telegram limit 4096)
    max_len = 4000
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                await client.post(url, json={
                    "chat_id": CONFIG.owner_id,
                    "text": chunk,
                })
    except Exception as e:
        core_logger.warning(f"Failed to forward to Telegram: {e}")


@app.post("/clear")
async def clear_session(req: ClearRequest, _=Depends(_check_auth)):
    chat_id = req.chat_id or CONFIG.owner_id or 0
    sessions.clear(chat_id)
    return {"status": "cleared"}


@app.get("/history")
async def get_history(chat_id: int = 0, _=Depends(_check_auth)):
    chat_id = chat_id or CONFIG.owner_id or 0
    session = sessions.get(chat_id)
    return {"messages": session.history}


# ── Sessions & Events ─────────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions(_=Depends(_check_auth)):
    conn = get_db()
    rows = conn.execute(
        "SELECT session_key, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return {"sessions": [dict(r) for r in rows]}


@app.get("/events")
async def get_events(session_key: str = "", limit: int = 100, _=Depends(_check_auth)):
    conn = get_db()
    rows = conn.execute(
        "SELECT event_type, data, created_at FROM agent_events WHERE session_key = ? ORDER BY id DESC LIMIT ?",
        (session_key, limit),
    ).fetchall()
    conn.close()
    events = [{"type": r["event_type"], "data": json.loads(r["data"]), "at": r["created_at"]} for r in rows]
    return {"events": list(reversed(events))}


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.get("/tasks")
async def list_tasks(_=Depends(_check_auth)):
    return {"tasks": get_scheduled_tasks()}


@app.post("/tasks")
async def create_task(req: TaskCreateRequest, _=Depends(_check_auth)):
    if not req.interval_minutes and not req.cron:
        raise HTTPException(status_code=400, detail="interval_minutes or cron required")
    conn = get_db()
    conn.execute(
        "INSERT INTO scheduled_tasks (name, cron, interval_minutes, prompt) VALUES (?, ?, ?, ?)",
        (req.name, req.cron, req.interval_minutes, req.prompt),
    )
    conn.commit()
    conn.close()
    return {"status": "created"}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, _=Depends(_check_auth)):
    conn = get_db()
    conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.patch("/tasks/{task_id}/toggle")
async def toggle_task(task_id: int, _=Depends(_check_auth)):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    conn.execute("UPDATE scheduled_tasks SET enabled = ? WHERE id = ?", (0 if row["enabled"] else 1, task_id))
    conn.commit()
    conn.close()
    return {"status": "toggled"}


# ── Files ─────────────────────────────────────────────────────────────────────

@app.get("/files")
async def list_files(path: str = "", _=Depends(_check_auth)):
    safe = _safe_path(path or ".")
    if not os.path.exists(safe):
        raise HTTPException(status_code=404, detail="Path not found")
    if os.path.isfile(safe):
        raise HTTPException(status_code=400, detail="Not a directory")

    entries = []
    for name in sorted(os.listdir(safe)):
        full = os.path.join(safe, name)
        rel = os.path.relpath(full, CONFIG.workspace)
        entries.append({
            "name": name,
            "path": rel,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": os.path.getsize(full) if os.path.isfile(full) else None,
            "modified": os.path.getmtime(full),
        })
    return {"path": os.path.relpath(safe, CONFIG.workspace), "entries": entries}


@app.get("/file")
async def read_file(path: str, _=Depends(_check_auth)):
    safe = _safe_path(path)
    if not os.path.isfile(safe):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = open(safe, errors="replace").read()
        return {"path": path, "content": content, "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/file")
async def write_file(req: WriteFileRequest, _=Depends(_check_auth)):
    safe = _safe_path(req.path)
    os.makedirs(os.path.dirname(safe), exist_ok=True)
    with open(safe, "w") as f:
        f.write(req.content)
    return {"status": "written", "size": len(req.content)}


@app.delete("/file")
async def delete_file(path: str = Query(...), _=Depends(_check_auth)):
    import shutil
    safe = _safe_path(path)
    if not os.path.exists(safe):
        raise HTTPException(status_code=404, detail="Not found")
    if os.path.isdir(safe):
        shutil.rmtree(safe)
    else:
        os.remove(safe)
    return {"status": "deleted"}


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings")
async def get_settings(_=Depends(_check_auth)):
    return {
        "model": CONFIG.model,
        "llm_base_url": CONFIG.llm_base_url,
        "llm_api_key": "***" if CONFIG.llm_api_key else "",
        "brave_api_key": "***" if CONFIG.brave_api_key else "",
        "memory_enabled": CONFIG.memory_enabled,
        "max_iterations": CONFIG.max_iterations,
        "command_timeout": CONFIG.command_timeout,
        "workspace": CONFIG.workspace,
        "owner_id": CONFIG.owner_id,
    }


@app.post("/settings")
async def update_settings(req: SettingsRequest, _=Depends(_check_auth)):
    """Write changed settings back to secrets/core.env."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "secrets", "core.env")
    if not os.path.exists(env_path):
        raise HTTPException(status_code=404, detail="secrets/core.env not found")

    lines = open(env_path).readlines()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    key_map = {
        "model": "MODEL", "llm_base_url": "LLM_BASE_URL", "llm_api_key": "LLM_API_KEY",
        "brave_api_key": "BRAVE_API_KEY", "memory_enabled": "MEMORY_ENABLED",
        "max_iterations": "MAX_ITERATIONS", "command_timeout": "COMMAND_TIMEOUT",
    }
    new_lines = []
    updated = set()
    for line in lines:
        written = False
        for field, env_key in key_map.items():
            if field in updates and line.startswith(f"{env_key}="):
                val = str(updates[field]).lower() if isinstance(updates[field], bool) else str(updates[field])
                new_lines.append(f"{env_key}={val}\n")
                updated.add(field)
                written = True
                break
        if not written:
            new_lines.append(line)

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    return {"status": "saved", "updated": list(updated), "note": "Restart core to apply changes"}


@app.post("/restart")
async def restart_core(_=Depends(_check_auth)):
    """Restart the core process by replacing the current process with a fresh one."""
    import sys
    import signal
    core_logger.info("Restart requested via admin UI")
    # Schedule a SIGTERM after responding — uvicorn will restart if supervisor is watching
    asyncio.get_event_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"status": "restarting"}


# ── Logs ──────────────────────────────────────────────────────────────────────

_LOG_FILES = {
    "core": "/tmp/localtaskclaw-core.log",
    "bot": "/tmp/localtaskclaw-bot.log",
}


@app.get("/logs/tail")
async def tail_logs(source: str = "core", lines: int = 200, _=Depends(_check_auth)):
    """Return last N lines from a log file."""
    log_path = _LOG_FILES.get(source)
    if not log_path:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}. Use: {list(_LOG_FILES)}")
    if not os.path.exists(log_path):
        return {"lines": [], "source": source}
    with open(log_path, errors="replace") as f:
        all_lines = f.readlines()
    return {"lines": [l.rstrip("\n") for l in all_lines[-lines:]], "source": source}


@app.get("/logs/stream")
async def stream_logs(source: str = "core", key: str = Query(default=""), x_api_key: str = Header(default="")):
    """SSE stream — tail -f a log file. Accepts key via query param (EventSource can't set headers)."""
    # Accept API key from either header or query param
    provided = key or x_api_key
    if CONFIG.api_secret and provided != CONFIG.api_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    log_path = _LOG_FILES.get(source)
    if not log_path:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

    return StreamingResponse(
        _tail_log_sse(log_path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _tail_log_sse(log_path: str) -> AsyncGenerator[str, None]:
    """Yield SSE events for new lines appended to log_path."""
    try:
        pos = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    except OSError:
        pos = 0

    while True:
        await asyncio.sleep(0.5)
        try:
            if not os.path.exists(log_path):
                continue
            size = os.path.getsize(log_path)
            if size < pos:
                pos = 0  # Log rotated
            if size > pos:
                with open(log_path, errors="replace") as f:
                    f.seek(pos)
                    new_data = f.read(size - pos)
                pos = size
                for line in new_data.splitlines():
                    if line.strip():
                        yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
        except OSError:
            pass


# ── Agents ────────────────────────────────────────────────────────────────────

@app.get("/agents")
async def list_agents(_=Depends(_check_auth)):
    return {"agents": get_agents()}


@app.post("/agents")
async def create_agent_endpoint(req: AgentCreateRequest, _=Depends(_check_auth)):
    agents = get_agents()
    if len(agents) >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 agents allowed")
    agent = create_agent(req.name, req.color, req.emoji, req.system_prompt)
    return agent


@app.patch("/agents/{agent_id}")
async def update_agent_endpoint(agent_id: int, req: AgentUpdateRequest, _=Depends(_check_auth)):
    updated = update_agent(agent_id, **req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")
    return updated


@app.delete("/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: int, _=Depends(_check_auth)):
    delete_agent(agent_id)
    return {"status": "deleted"}


# ── Kanban ────────────────────────────────────────────────────────────────────

@app.get("/kanban")
async def list_kanban(_=Depends(_check_auth)):
    return {"tasks": get_kanban_tasks()}


@app.post("/kanban/tasks")
async def create_kanban_task_endpoint(req: KanbanTaskCreateRequest, _=Depends(_check_auth)):
    task = create_kanban_task(req.title, req.description, req.agent_id, req.column)
    return task


@app.patch("/kanban/tasks/{task_id}")
async def update_kanban_task_endpoint(task_id: int, req: KanbanTaskUpdateRequest, _=Depends(_check_auth)):
    task = update_kanban_task(task_id, **req.model_dump(exclude_none=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/kanban/tasks/{task_id}/move")
async def move_kanban_task(task_id: int, req: KanbanTaskMoveRequest, _=Depends(_check_auth)):
    task = update_kanban_task(task_id, column=req.column, position=req.position or 0)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/kanban/tasks/{task_id}")
async def delete_kanban_task_endpoint(task_id: int, _=Depends(_check_auth)):
    delete_kanban_task(task_id)
    return {"status": "deleted"}


@app.post("/kanban/tasks/{task_id}/run")
async def run_kanban_task(task_id: int, _=Depends(_check_auth)):
    """Run agent on a kanban task. Moves it to in_progress, then review when done."""
    tasks = get_kanban_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Move to in_progress
    update_kanban_task(task_id, column="in_progress", status="running")

    # Build prompt with agent identity prepended
    agent_identity = ""
    if task.get("agent_name"):
        agent_identity = f"You are {task['agent_name']}."
        if task.get("agent_system_prompt") or task.get("system_prompt"):
            sp = task.get("system_prompt") or ""
            agent_identity += f"\n{sp}"

    prompt = task["description"] or task["title"]
    full_prompt = f"{agent_identity}\n\n---\n\nTask: {task['title']}\n\n{task['description']}".strip() if agent_identity else f"Task: {task['title']}\n\n{task['description']}".strip()

    async def _run():
        try:
            # Use a dedicated chat_id per task to isolate session
            chat_id = -(task_id + 100000)
            result = await run_agent(chat_id, full_prompt)
            artifact_md = f"# {task['title']}\n\n{result.text}\n"
            # Save .md artifact to workspace
            artifact_filename = f"task_{task_id}_{task['title'][:30].replace(' ', '_').lower()}.md"
            artifact_path = os.path.join(CONFIG.workspace, "artifacts", artifact_filename)
            os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
            with open(artifact_path, "w") as f:
                f.write(artifact_md)
            update_kanban_task(task_id, column="review", status="done", artifact=artifact_path)
        except Exception as e:
            core_logger.error(f"Kanban task {task_id} run failed: {e}")
            update_kanban_task(task_id, status="error", column="backlog")

    asyncio.create_task(_run())
    return {"status": "started", "task_id": task_id}


@app.get("/kanban/tasks/{task_id}/artifact")
async def get_kanban_artifact(task_id: int, _=Depends(_check_auth)):
    tasks = get_kanban_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.get("artifact"):
        raise HTTPException(status_code=404, detail="No artifact yet")
    try:
        content = open(task["artifact"], errors="replace").read()
        return {"content": content, "path": task["artifact"]}
    except Exception:
        # Return stored artifact text if file missing
        return {"content": task.get("artifact", ""), "path": None}
