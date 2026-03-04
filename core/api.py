"""FastAPI app — agent endpoint consumed by bot and admin UI."""

import json
import asyncio
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import CONFIG
from logger import core_logger
from agent.run import run_agent
from agent.session import sessions
from db import get_db, get_scheduled_tasks

app = FastAPI(title="LocalClaw Core", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_auth(x_api_key: str = Header(default="")):
    if CONFIG.api_secret and x_api_key != CONFIG.api_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ChatRequest(BaseModel):
    message: str
    chat_id: int = 0
    stream: bool = False


class ClearRequest(BaseModel):
    chat_id: int = 0


@app.get("/health")
async def health():
    return {"status": "ok", "model": CONFIG.model}


@app.post("/chat")
async def chat(req: ChatRequest, _=Depends(_check_auth)):
    chat_id = req.chat_id or CONFIG.owner_id or 0

    if req.stream:
        return StreamingResponse(
            _stream_agent(chat_id, req.message),
            media_type="text/event-stream",
        )

    result = await run_agent(chat_id, req.message)
    return {
        "text": result.text,
        "tool_events": result.tool_events,
        "tokens": {
            "prompt": result.total_prompt_tokens,
            "completion": result.total_completion_tokens,
        },
    }


async def _stream_agent(chat_id: int, message: str) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event_type: str, data: dict):
        await queue.put((event_type, data))

    async def run():
        try:
            await run_agent(chat_id, message, on_event=on_event)
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(run())

    while True:
        item = await queue.get()
        if item is None:
            yield "data: [DONE]\n\n"
            break
        event_type, data = item
        yield f"data: {json.dumps({'type': event_type, **data})}\n\n"


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


@app.get("/tasks")
async def list_tasks(_=Depends(_check_auth)):
    return {"tasks": get_scheduled_tasks()}


@app.get("/events")
async def get_events(session_key: str = "", limit: int = 50, _=Depends(_check_auth)):
    conn = get_db()
    rows = conn.execute(
        "SELECT event_type, data, created_at FROM agent_events WHERE session_key = ? ORDER BY id DESC LIMIT ?",
        (session_key, limit),
    ).fetchall()
    conn.close()
    import json as _json
    events = [{"type": r["event_type"], "data": _json.loads(r["data"]), "at": r["created_at"]} for r in rows]
    return {"events": list(reversed(events))}
