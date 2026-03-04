"""Memory tool — read/write MEMORY.md in workspace."""

import os
from config import CONFIG
from logger import tool_logger
from models import ToolResult, ToolContext


def _memory_path(cwd: str) -> str:
    return os.path.join(cwd, "MEMORY.md")


async def tool_memory(args: dict, ctx: ToolContext) -> ToolResult:
    action = args.get("action", "read")
    content = args.get("content", "")

    path = _memory_path(ctx.cwd)

    if action == "read":
        if not os.path.exists(path):
            return ToolResult(True, output="(MEMORY.md is empty)")
        text = open(path).read()
        return ToolResult(True, output=text or "(empty)")

    elif action == "write":
        if not content:
            return ToolResult(False, error="content is required for write")
        os.makedirs(ctx.cwd, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return ToolResult(True, output=f"Memory saved ({len(content)} chars)")

    elif action == "append":
        if not content:
            return ToolResult(False, error="content is required for append")
        existing = open(path).read() if os.path.exists(path) else ""
        with open(path, "w") as f:
            f.write(existing + ("\n" if existing else "") + content)
        return ToolResult(True, output="Memory updated")

    else:
        return ToolResult(False, error=f"Unknown action: {action}. Use read/write/append")


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "memory",
        "description": "Read or update your persistent memory (MEMORY.md). Use to remember facts, preferences, and notes across sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "read — get current memory, write — replace entirely, append — add to end",
                    "enum": ["read", "write", "append"],
                },
                "content": {
                    "type": "string",
                    "description": "Content to write or append (not needed for read)",
                },
            },
            "required": ["action"],
        },
    },
}
