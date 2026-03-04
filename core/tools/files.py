"""File management tools — read, write, list, delete."""

import os
import shutil
from config import CONFIG
from logger import tool_logger
from models import ToolResult, ToolContext


def _safe_path(cwd: str, path: str) -> str | None:
    """Resolve path relative to cwd, block traversal outside workspace."""
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        resolved = os.path.realpath(os.path.join(cwd, path))

    workspace = os.path.realpath(CONFIG.workspace)
    if not resolved.startswith(workspace):
        return None
    return resolved


async def tool_read_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = args.get("path", "")
    safe = _safe_path(ctx.cwd, path)
    if not safe:
        return ToolResult(False, error="🚫 Path outside workspace")
    if not os.path.exists(safe):
        return ToolResult(False, error=f"File not found: {path}")
    if os.path.isdir(safe):
        return ToolResult(False, error=f"Is a directory, use list_files")

    try:
        with open(safe, "r", errors="replace") as f:
            content = f.read()
        if len(content) > CONFIG.max_tool_output:
            content = content[:CONFIG.max_tool_output] + "\n...[TRUNCATED]..."
        return ToolResult(True, output=content)
    except Exception as e:
        return ToolResult(False, error=str(e))


async def tool_write_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = args.get("path", "")
    content = args.get("content", "")
    safe = _safe_path(ctx.cwd, path)
    if not safe:
        return ToolResult(False, error="🚫 Path outside workspace")

    try:
        os.makedirs(os.path.dirname(safe), exist_ok=True)
        with open(safe, "w") as f:
            f.write(content)
        size = os.path.getsize(safe)
        return ToolResult(True, output=f"Written {size} bytes to {path}")
    except Exception as e:
        return ToolResult(False, error=str(e))


async def tool_list_files(args: dict, ctx: ToolContext) -> ToolResult:
    path = args.get("path", ".")
    safe = _safe_path(ctx.cwd, path)
    if not safe:
        return ToolResult(False, error="🚫 Path outside workspace")
    if not os.path.exists(safe):
        return ToolResult(False, error=f"Directory not found: {path}")

    try:
        entries = []
        for name in sorted(os.listdir(safe)):
            full = os.path.join(safe, name)
            if os.path.isdir(full):
                entries.append(f"[dir]  {name}/")
            else:
                size = os.path.getsize(full)
                entries.append(f"[file] {name} ({size} bytes)")
        return ToolResult(True, output="\n".join(entries) or "(empty directory)")
    except Exception as e:
        return ToolResult(False, error=str(e))


async def tool_delete_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = args.get("path", "")
    safe = _safe_path(ctx.cwd, path)
    if not safe:
        return ToolResult(False, error="🚫 Path outside workspace")
    if not os.path.exists(safe):
        return ToolResult(False, error=f"Not found: {path}")

    try:
        if os.path.isdir(safe):
            shutil.rmtree(safe)
        else:
            os.remove(safe)
        return ToolResult(True, output=f"Deleted: {path}")
    except Exception as e:
        return ToolResult(False, error=str(e))


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to workspace or absolute)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates directories as needed)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: workspace root)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                },
                "required": ["path"],
            },
        },
    },
]
