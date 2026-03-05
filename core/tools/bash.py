"""Bash command execution — subprocess with restricted environment."""

import asyncio
import os
from config import CONFIG
from logger import tool_logger
from models import ToolResult, ToolContext
from security import check_command, sanitize_output


def _safe_env(cwd: str) -> dict:
    """Minimal safe environment — no secrets."""
    return {
        "HOME": os.path.expanduser("~"),
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "SHELL": "/bin/bash",
        "TERM": "xterm-256color",
        "PWD": cwd,
        "LANG": "en_US.UTF-8",
    }


async def tool_run_command(args: dict, ctx: ToolContext) -> ToolResult:
    command = args.get("command", "").strip()
    if not command:
        return ToolResult(False, error="No command provided")

    check = check_command(command)
    if check.blocked:
        return ToolResult(False, error=f"🚫 BLOCKED: {check.reason}")
    if check.needs_confirm:
        # Return a special error asking for confirmation via natural language
        return ToolResult(
            False,
            error=f"⚠️ REQUIRES CONFIRMATION: {check.reason}\n\nThis command is potentially destructive. Please confirm explicitly: type 'yes, run: {command}' or clarify the task.",
            metadata={"needs_confirm": True, "command": command},
        )

    tool_logger.info(f"Exec: {command[:120]}")

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=ctx.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_safe_env(ctx.cwd),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=CONFIG.command_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(False, error=f"Timeout after {CONFIG.command_timeout}s")

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        combined = out + ("\n" + err if err else "")

        if len(combined) > CONFIG.max_tool_output:
            half = CONFIG.max_tool_output // 2
            combined = combined[:half] + "\n\n...[TRIMMED]...\n\n" + combined[-half:]

        success = proc.returncode == 0
        if success:
            return ToolResult(True, output=combined or "(empty output)")
        else:
            return ToolResult(False, error=combined or f"Exit code {proc.returncode}")

    except Exception as e:
        tool_logger.error(f"Command error: {e}")
        return ToolResult(False, error=str(e))


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Execute a bash shell command. Use for file operations, running scripts, checking processes, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
            },
            "required": ["command"],
        },
    },
}
