"""Session management — in-memory + SQLite persistence."""

import os
from config import CONFIG
from logger import agent_logger
from db import ensure_session, load_messages, save_messages
from agent._types import Session


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def _key(self, chat_id: int) -> str:
        return f"owner_{chat_id}"

    def get(self, chat_id: int) -> Session:
        key = self._key(chat_id)
        if key not in self._sessions:
            cwd = os.path.join(CONFIG.workspace, "main")
            os.makedirs(cwd, exist_ok=True)
            ensure_session(key)
            history = load_messages(key)
            self._sessions[key] = Session(session_key=key, cwd=cwd, history=history)
            agent_logger.info(f"Session loaded: {key}, {len(history)} messages")
        return self._sessions[key]

    def save(self, chat_id: int):
        key = self._key(chat_id)
        if key in self._sessions:
            save_messages(key, self._sessions[key].history)

    def clear(self, chat_id: int):
        key = self._key(chat_id)
        if key in self._sessions:
            self._sessions[key].history = []
            save_messages(key, [])
            agent_logger.info(f"Session cleared: {key}")


sessions = SessionManager()
