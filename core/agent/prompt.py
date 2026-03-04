"""System prompt loading and formatting."""

import os
from pathlib import Path
from datetime import datetime, timezone


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_system_prompt() -> str:
    path = Path(__file__).parent.parent / "system.txt"
    if path.exists():
        return path.read_text()
    return _fallback_prompt()


def format_system_prompt(template: str, cwd: str, tools_list: str, skills_list: str = "") -> str:
    prompt = template
    prompt = prompt.replace("{{cwd}}", cwd)
    prompt = prompt.replace("{{date}}", _now_str())
    prompt = prompt.replace("{{tools}}", tools_list)
    prompt = prompt.replace("{{skills}}", skills_list or "(none)")
    return prompt


def _fallback_prompt() -> str:
    return """You are a helpful personal AI assistant with access to a Linux environment.

You can execute shell commands, manage files, search the web, and set reminders.
Be concise, helpful, and always follow through — call tools in the same response.

Current directory: {{cwd}}
Date/time: {{date}}

Available tools:
{{tools}}
"""
