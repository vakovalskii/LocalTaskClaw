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

# Track running kanban asyncio tasks for cancellation
_kanban_running: dict[int, asyncio.Task] = {}
from db import (
    get_db, get_scheduled_tasks,
    get_agents, create_agent, update_agent, delete_agent,
    get_kanban_boards, create_kanban_board, update_kanban_board, delete_kanban_board,
    get_kanban_tasks, create_kanban_task, update_kanban_task, delete_kanban_task,
)

app = FastAPI(title="LocalTaskClaw Core", version="0.1.0")


@app.on_event("startup")
async def _on_startup():
    from db import init_db
    init_db()
    try:
        from tools.mcp import init_mcp
        await init_mcp(CONFIG.workspace)
    except Exception as e:
        core_logger.warning(f"MCP init skipped: {e}")


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
    role: str = "worker"
    allowed_tools: list | None = None
    allowed_paths: list | None = None

class AgentUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None
    emoji: str | None = None
    system_prompt: str | None = None
    role: str | None = None
    allowed_tools: list | None = None   # None = "don't change"; pass [] to clear (allow all)
    allowed_paths: list | None = None

class KanbanBoardCreateRequest(BaseModel):
    name: str
    emoji: str = "📋"

class KanbanBoardUpdateRequest(BaseModel):
    name: str | None = None
    emoji: str | None = None

class KanbanTaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    agent_id: int | None = None
    column: str = "backlog"
    repeat_minutes: int = 0
    board_id: int = 1

class KanbanTaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    agent_id: int | None = None
    column: str | None = None
    position: int | None = None
    repeat_minutes: int | None = None

class KanbanTaskMoveRequest(BaseModel):
    column: str
    position: int | None = None

class SpawnProjectRequest(BaseModel):
    description: str
    stream: bool = False
    board_id: int | None = None  # None = create new board


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


async def _stream_agent(
    chat_id: int, message: str, forward: bool = False, extra_system: str = ""
) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event_type: str, data: dict):
        await queue.put((event_type, data))

    asyncio.create_task(
        _run_and_signal(chat_id, message, on_event, queue, forward=forward, extra_system=extra_system)
    )

    while True:
        item = await queue.get()
        if item is None:
            yield "data: [DONE]\n\n"
            break
        event_type, data = item
        yield f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


async def _run_and_signal(chat_id, message, on_event, queue, forward=False, extra_system=""):
    try:
        result = await run_agent(chat_id, message, on_event=on_event, extra_system=extra_system)
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


# ── Version & Update ─────────────────────────────────────────────────────────

def _get_local_version() -> dict:
    """Get current git commit info."""
    import subprocess
    app_dir = os.path.join(os.path.dirname(__file__), "..")
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=app_dir, stderr=subprocess.DEVNULL
        ).decode().strip()
        full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=app_dir, stderr=subprocess.DEVNULL
        ).decode().strip()
        date = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci"], cwd=app_dir, stderr=subprocess.DEVNULL
        ).decode().strip()
        subject = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"], cwd=app_dir, stderr=subprocess.DEVNULL
        ).decode().strip()
        return {"hash": full, "short": short, "date": date, "message": subject}
    except Exception:
        return {"hash": "", "short": "unknown", "date": "", "message": ""}


@app.get("/version")
async def get_version():
    """Return current local version and check GitHub for latest."""
    local = _get_local_version()
    remote = {"hash": "", "short": "", "date": "", "message": ""}
    update_available = False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.github.com/repos/vakovalskii/LocalTaskClaw/commits/main",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                remote = {
                    "hash": data["sha"],
                    "short": data["sha"][:7],
                    "date": data["commit"]["committer"]["date"],
                    "message": data["commit"]["message"].split("\n")[0],
                }
                update_available = (local["hash"] != remote["hash"] and local["hash"] != "")
    except Exception as e:
        core_logger.warning(f"Failed to check remote version: {e}")

    return {
        "local": local,
        "remote": remote,
        "update_available": update_available,
    }


@app.post("/update")
async def run_update(_=Depends(_check_auth)):
    """Run update.sh to pull latest code and restart services."""
    import subprocess
    update_script = os.path.join(os.path.dirname(__file__), "..", "update.sh")
    if not os.path.isfile(update_script):
        raise HTTPException(status_code=404, detail="update.sh not found")

    core_logger.info("Update triggered via admin UI")
    try:
        result = subprocess.run(
            ["bash", update_script, "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            core_logger.error(f"Update failed: {output}")
            return {"status": "error", "output": output}
        core_logger.info(f"Update success: {output}")
        return {"status": "ok", "output": output}
    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "Update timed out (120s)"}
    except Exception as e:
        return {"status": "error", "output": str(e)}


@app.post("/seed-demo")
async def seed_demo(_=Depends(_check_auth)):
    """Run seed_kanban.py to populate demo agents and tasks."""
    import subprocess
    seed_script = os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_kanban.py")
    if not os.path.isfile(seed_script):
        raise HTTPException(status_code=404, detail="seed_kanban.py not found")

    venv_python = os.path.join(os.path.dirname(__file__), "..", "..", "venv", "bin", "python")
    python_cmd = venv_python if os.path.isfile(venv_python) else "python3"

    core_logger.info("Seed demo triggered via API")
    try:
        result = subprocess.run(
            [python_cmd, seed_script, "--reset"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "API_URL": f"http://localhost:{CONFIG.api_port}", "API_SECRET": CONFIG.api_secret},
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            return {"status": "error", "output": output}
        return {"status": "ok", "output": output}
    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "Seed timed out (30s)"}
    except Exception as e:
        return {"status": "error", "output": str(e)}


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
    agent = create_agent(req.name, req.color, req.emoji, req.system_prompt, req.role)
    return agent


@app.patch("/agents/{agent_id}")
async def update_agent_endpoint(agent_id: int, req: AgentUpdateRequest, _=Depends(_check_auth)):
    # Use exclude_unset so we can tell the difference between "not sent" vs "sent as null"
    fields = req.model_dump(exclude_unset=True)
    updated = update_agent(agent_id, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")
    return updated


@app.delete("/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: int, _=Depends(_check_auth)):
    delete_agent(agent_id)
    return {"status": "deleted"}


@app.get("/agents/tools")
async def list_all_tools(_=Depends(_check_auth)):
    """Return all available tool names with descriptions."""
    from tools import get_tool_definitions
    defs = get_tool_definitions()
    return {"tools": [
        {"name": t["function"]["name"], "description": t["function"].get("description", "")}
        for t in defs
    ]}


@app.get("/agents/{agent_id}/prompt-preview")
async def agent_prompt_preview(agent_id: int, _=Depends(_check_auth)):
    """Return the full assembled system prompt that this agent will see."""
    agents = get_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from agent.prompt import load_system_prompt, format_system_prompt
    from agent.skills import load_skills
    from tools import get_tool_definitions

    tool_defs = get_tool_definitions()
    allowed = agent.get("allowed_tools")
    if allowed:
        allowed_set = set(allowed)
        tool_defs = [t for t in tool_defs if t["function"]["name"] in allowed_set]

    tools_list = "\n".join(
        f"- {t['function']['name']}: {t['function'].get('description', '')}"
        for t in tool_defs
    )
    skills_list = load_skills(CONFIG.workspace)
    template = load_system_prompt()
    base_prompt = format_system_prompt(template, cwd=CONFIG.workspace, tools_list=tools_list, skills_list=skills_list)

    extra_parts = []
    if agent.get("name"):
        extra_parts.append(f"Your name: {agent['name']} {agent.get('emoji', '')}")
    if agent.get("system_prompt"):
        extra_parts.append(agent["system_prompt"])
    if CONFIG.owner_id:
        extra_parts.append(f"Owner Telegram ID: {CONFIG.owner_id}")
    if agent.get("allowed_paths"):
        extra_parts.append(f"Allowed file paths: {', '.join(agent['allowed_paths'])}")

    extra_system = "\n".join(extra_parts)
    full_prompt = (extra_system + "\n\n---\n\n" + base_prompt) if extra_system else base_prompt
    full_prompt += f"\n\nWorkspace: {CONFIG.workspace}\n\nYou are a focused task agent. Complete the assigned task directly."

    return {
        "full_prompt": full_prompt,
        "agent_section": extra_system,
        "base_section_length": len(base_prompt),
        "tools_count": len(tool_defs),
    }


# ── Kanban boards ─────────────────────────────────────────────────────────────

@app.get("/kanban/boards")
async def list_boards(_=Depends(_check_auth)):
    return {"boards": get_kanban_boards()}


@app.post("/kanban/boards")
async def create_board(req: KanbanBoardCreateRequest, _=Depends(_check_auth)):
    return create_kanban_board(req.name, req.emoji)


@app.patch("/kanban/boards/{board_id}")
async def update_board(board_id: int, req: KanbanBoardUpdateRequest, _=Depends(_check_auth)):
    board = update_kanban_board(board_id, req.name, req.emoji)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@app.delete("/kanban/boards/{board_id}")
async def delete_board(board_id: int, _=Depends(_check_auth)):
    if board_id == 1:
        raise HTTPException(status_code=400, detail="Cannot delete the default board")
    try:
        delete_kanban_board(board_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


# ── Kanban tasks ───────────────────────────────────────────────────────────────

@app.get("/kanban")
async def list_kanban(board_id: int = Query(default=1), _=Depends(_check_auth)):
    return {"tasks": get_kanban_tasks(board_id)}


@app.post("/kanban/tasks")
async def create_kanban_task_endpoint(req: KanbanTaskCreateRequest, _=Depends(_check_auth)):
    task = create_kanban_task(req.title, req.description, req.agent_id, req.column, req.repeat_minutes, req.board_id)
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

    # Build extra system prompt: agent identity + owner context
    extra_parts = []
    if task.get("agent_name"):
        extra_parts.append(f"Your name: {task['agent_name']}")
        if task.get("agent_emoji"):
            extra_parts[-1] += f" {task['agent_emoji']}"
    if task.get("agent_system_prompt"):
        extra_parts.append(task["agent_system_prompt"])
    if CONFIG.owner_id:
        extra_parts.append(f"Owner Telegram ID: {CONFIG.owner_id}")
    extra_system = "\n".join(extra_parts)

    task_prompt = f"Task: {task['title']}\n\n{task['description']}".strip()
    repeat_minutes = task.get("repeat_minutes", 0) or 0

    # Resolve agent restrictions from DB
    import json as _json
    _raw_tools = task.get("agent_allowed_tools")
    _raw_paths = task.get("agent_allowed_paths")
    agent_allowed_tools = _json.loads(_raw_tools) if isinstance(_raw_tools, str) else _raw_tools
    agent_allowed_paths = _json.loads(_raw_paths) if isinstance(_raw_paths, str) else _raw_paths

    # Human-readable labels for common tools
    _TOOL_LABELS = {
        "search_web": "🔍 search",
        "fetch_page": "🌐 reading page",
        "read_file": "📄 reading file",
        "write_file": "💾 writing file",
        "list_files": "📁 listing files",
        "delete_file": "🗑 deleting file",
        "kanban_list": "📋 viewing board",
        "kanban_run": "▶ starting task",
        "kanban_verify": "✅ verifying",
        "kanban_report": "📊 report",
        "kanban_read_result": "📖 reading result",
        "kanban_create": "➕ creating task",
        "kanban_create_agent": "🤖 creating agent",
        "telegram_notify": "💬 notification",
        "python_eval": "🐍 running code",
        "shell_exec": "⚡ executing command",
    }

    async def _on_kanban_event(event_type: str, data: dict):
        if event_type == "tool_start":
            name = data.get("name", "")
            label = _TOOL_LABELS.get(name, f"🔧 {name}")
            # Add key arg for context (e.g. filename or query)
            args = data.get("args", {})
            detail = (
                args.get("query") or args.get("path") or args.get("url")
                or args.get("task_id") or args.get("name") or ""
            )
            if detail:
                label += f": {str(detail)[:40]}"
            update_kanban_task(task_id, last_action=label)
        elif event_type == "tool_done":
            # Show brief success/fail hint
            success = data.get("success", True)
            name = data.get("name", "")
            base = _TOOL_LABELS.get(name, f"🔧 {name}")
            update_kanban_task(task_id, last_action=base + (" ✓" if success else " ✗"))

    async def _run():
        try:
            # Fresh session per run — clear history so old runs don't bleed in
            chat_id = -(task_id + 100000)
            sessions.clear(chat_id)
            update_kanban_task(task_id, last_action="🤔 thinking...")
            result = await run_agent(
                chat_id, task_prompt, task_mode=True, extra_system=extra_system,
                allowed_tools=agent_allowed_tools, allowed_paths=agent_allowed_paths,
                on_event=_on_kanban_event,
            )
            artifact_md = f"# {task['title']}\n\n{result.text}\n"
            artifact_filename = f"task_{task_id}_{task['title'][:30].replace(' ', '_').lower()}.md"
            artifact_path = os.path.join(CONFIG.workspace, "artifacts", artifact_filename)
            os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
            with open(artifact_path, "w") as f:
                f.write(artifact_md)
            # If repeat is set — go back to backlog; otherwise move to review
            if repeat_minutes > 0:
                update_kanban_task(task_id, column="backlog", status="idle", artifact=artifact_path, last_action=None)
                core_logger.info(f"Kanban task {task_id} will repeat in {repeat_minutes}m")
                await asyncio.sleep(repeat_minutes * 60)
                # Re-trigger via internal HTTP so the full run path is reused
                import httpx
                url = f"http://localhost:{CONFIG.api_port}/kanban/tasks/{task_id}/run"
                headers = {"X-Api-Key": CONFIG.api_secret} if CONFIG.api_secret else {}
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(url, headers=headers)
                except Exception as e:
                    core_logger.warning(f"Repeat trigger failed for task {task_id}: {e}")
            else:
                update_kanban_task(task_id, column="review", status="done", artifact=artifact_path, last_action=None)
        except asyncio.CancelledError:
            core_logger.info(f"Kanban task {task_id} cancelled")
            update_kanban_task(task_id, status="idle", column="backlog", last_action=None)
        except Exception as e:
            core_logger.error(f"Kanban task {task_id} run failed: {e}")
            update_kanban_task(task_id, status="error", column="backlog", last_action=None)
        finally:
            _kanban_running.pop(task_id, None)

    t = asyncio.create_task(_run())
    _kanban_running[task_id] = t
    return {"status": "started", "task_id": task_id}


@app.post("/kanban/tasks/{task_id}/cancel")
async def cancel_kanban_task(task_id: int, _=Depends(_check_auth)):
    """Cancel a running kanban task."""
    t = _kanban_running.get(task_id)
    if t and not t.done():
        t.cancel()
        return {"status": "cancelled", "task_id": task_id}
    # Task not running in memory — just reset status in DB
    update_kanban_task(task_id, status="idle", column="backlog")
    return {"status": "reset", "task_id": task_id}


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


# ── Spawn project ──────────────────────────────────────────────────────────────

_SPAWNER_SYSTEM = """\
<role>You are a project spawner.</role>

<instructions>
You receive a task/project description and must produce everything in a single response:

1. DESIGN a team: 2-4 specialized worker agents + 1 orchestrator.
2. CREATE each agent via kanban_create_agent (name, emoji, color, role, system_prompt).
   - Workers: role="worker", detailed system_prompt explaining WHAT to do and WHERE to save results (artifacts/).
   - Orchestrator: role="orchestrator", system_prompt with the standard algorithm (start → verify → report).
3. CREATE tasks for workers via kanban_create (title, description, agent_id, column="backlog").
   - Clear task description, specify the artifact filename.
4. CREATE a task for the orchestrator via kanban_create (repeat_minutes=5 is NOT available in kanban_create).
   - If repeat is needed, create the task first, then update it manually (kanban_update with repeat_minutes if necessary).
5. START the orchestrator via kanban_run.

Choose meaningful specializations for the project. Do not create generic agents.
After creating everything, output a brief summary: who was created and what they will do.
</instructions>
"""


@app.post("/spawn")
async def spawn_project(req: SpawnProjectRequest, _=Depends(_check_auth)):
    """
    Natural-language project spawn: one description → new board + agents + tasks + orchestrator running.
    Streams SSE when req.stream=True.
    """
    # Create a new board for this project (name = first ~30 chars of description)
    board_name = req.description[:40].strip().rstrip(".,!?") or "Project"
    board = create_kanban_board(board_name, "🚀")
    board_id = board["id"]

    # Build spawner system prompt with the target board_id
    spawner_system = _SPAWNER_SYSTEM + f"\n\nIMPORTANT: all kanban_create calls must pass board_id={board_id}. This is a new board created specifically for this project."

    spawn_session = -(999000 + board_id)  # unique session per board

    if req.stream:
        return StreamingResponse(
            _stream_agent(spawn_session, req.description, forward=False, extra_system=spawner_system),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=None,
        )

    result = await run_agent(spawn_session, req.description, extra_system=spawner_system)
    return {"text": result.text, "tool_events": result.tool_events, "board_id": board_id}
