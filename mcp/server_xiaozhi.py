# server_xiaozhi.py
"""
MCP Server for LocalTaskClawXiaozhi integration.
Provides tools for managing kanban tasks, agents, and projects via MCP protocol.
"""

from fastmcp import FastMCP
import sys
import logging
import os
import httpx
import json

logger = logging.getLogger('XiaozhiMCP')

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# Configuration from environment
XIAOZHI_BASE_URL = os.environ.get("XIAOZHI_BASE_URL", "http://localhost:11387")
XIAOZHI_API_KEY = os.environ.get("XIAOZHI_API_KEY", "")

# Create MCP server
mcp = FastMCP("LocalTaskClawXiaozhi")


def _get_headers() -> dict:
    """Get HTTP headers with API key if configured."""
    headers = {"Content-Type": "application/json"}
    if XIAOZHI_API_KEY:
        headers["X-Api-Key"] = XIAOZHI_API_KEY
    return headers


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def xiaozhi_kanban_list(column: str = None) -> dict:
    """
    List all kanban tasks from LocalTaskClawXiaozhi.
    
    Args:
        column: Optional filter by column (backlog, in_progress, review, done, needs_human)
    
    Returns:
        Dictionary with tasks and agents lists
    """
    try:
        path = "/kanban"
        if column:
            path += f"?column={column}"
        result = httpx.get(f"{XIAOZHI_BASE_URL}{path}", headers=_get_headers()).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error listing kanban: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_kanban_create(
    title: str,
    description: str = "",
    agent_id: int = None,
    column: str = "backlog",
    board_id: int = 1,
    repeat_minutes: int = 0
) -> dict:
    """
    Create a new kanban task in LocalTaskClawXiaozhi.
    
    Args:
        title: Task title (required)
        description: Task description
        agent_id: ID of assigned agent (optional)
        column: Column to place task (backlog, in_progress, review, done, needs_human)
        board_id: Kanban board ID (default: 1)
        repeat_minutes: Auto-repeat interval in minutes (0 = disabled)
    
    Returns:
        Created task data
    """
    try:
        data = {
            "title": title,
            "description": description,
            "agent_id": agent_id,
            "column": column,
            "board_id": board_id,
            "repeat_minutes": repeat_minutes
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/kanban/tasks",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating kanban task: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_kanban_move(task_id: int, column: str) -> dict:
    """
    Move a kanban task to a different column.
    
    Args:
        task_id: Task ID to move
        column: Target column (backlog, in_progress, review, done, needs_human)
    
    Returns:
        Updated task data
    """
    try:
        data = {"column": column}
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/kanban/tasks/{task_id}/move",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error moving task: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_kanban_run(task_id: int) -> dict:
    """
    Start the assigned agent on a kanban task.
    
    Args:
        task_id: Task ID to run
    
    Returns:
        Status of agent start
    """
    try:
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/kanban/tasks/{task_id}/run",
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error running task: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_kanban_verify(task_id: int, approved: bool, comment: str) -> dict:
    """
    Approve or reject a completed task after reviewing its result.
    
    Args:
        task_id: Task ID to verify
        approved: True to approve, False to reject
        comment: Feedback comment (required)
    
    Returns:
        Verification result
    """
    try:
        data = {"approved": approved, "comment": comment}
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/kanban/tasks/{task_id}/verify",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error verifying task: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_agents_list() -> dict:
    """
    List all available agents in LocalTaskClawXiaozhi.
    
    Returns:
        List of agents with their IDs, names, roles, and capabilities
    """
    try:
        result = httpx.get(
            f"{XIAOZHI_BASE_URL}/agents",
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_agent_create(
    name: str,
    system_prompt: str,
    role: str = "worker",
    emoji: str = "🤖",
    color: str = "#6366f1"
) -> dict:
    """
    Create a new agent in LocalTaskClawXiaozhi.
    
    Args:
        name: Agent display name
        system_prompt: Full system prompt for this agent
        role: Agent role (worker or orchestrator)
        emoji: Single emoji for agent avatar
        color: Hex color code (e.g., #3b82f6)
    
    Returns:
        Created agent data with ID
    """
    try:
        data = {
            "name": name,
            "system_prompt": system_prompt,
            "role": role,
            "emoji": emoji,
            "color": color
        }
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/agents",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_chat(message: str, chat_id: int = 0, stream: bool = False) -> dict:
    """
    Send a message to the LocalTaskClawXiaozhi agent.
    
    Args:
        message: Message to send
        chat_id: Chat/session ID (default: 0)
        stream: Enable streaming response (default: False)
    
    Returns:
        Agent response
    """
    try:
        data = {
            "message": message,
            "chat_id": chat_id,
            "stream": stream,
            "source": "mcp"
        }
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/chat",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error sending chat: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_boards_list() -> dict:
    """
    List all kanban boards in LocalTaskClawXiaozhi.
    
    Returns:
        List of boards with their IDs and names
    """
    try:
        result = httpx.get(
            f"{XIAOZHI_BASE_URL}/kanban/boards",
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error listing boards: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_board_create(name: str, emoji: str = "📋") -> dict:
    """
    Create a new kanban board (project).
    
    Args:
        name: Board/project name
        emoji: Single emoji for board icon
    
    Returns:
        Created board data with ID
    """
    try:
        data = {"name": name, "emoji": emoji}
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/kanban/boards",
            json=data,
            headers=_get_headers()
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating board: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_project_spawn(
    description: str,
    board_id: int = None,
    stream: bool = False
) -> dict:
    """
    Spawn a new project with automatic agent and task creation.
    This is a high-level tool that creates a board, orchestrator agent,
    and initial tasks based on the project description.
    
    Args:
        description: Project description and requirements
        board_id: Existing board ID (optional, creates new if not provided)
        stream: Enable streaming response
    
    Returns:
        Project spawn result with created resources
    """
    try:
        data = {
            "description": description,
            "board_id": board_id,
            "stream": stream
        }
        data = {k: v for k, v in data.items() if v is not None}
        
        result = httpx.post(
            f"{XIAOZHI_BASE_URL}/spawn",
            json=data,
            headers=_get_headers(),
            timeout=60
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error spawning project: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_health() -> dict:
    """
    Check LocalTaskClawXiaozhi server health status.
    
    Returns:
        Health status with model and workspace info
    """
    try:
        result = httpx.get(
            f"{XIAOZHI_BASE_URL}/health",
            timeout=5
        ).json()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"success": False, "error": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger.info(f"Starting Xiaozhi MCP Server")
    logger.info(f"Xiaozhi API URL: {XIAOZHI_BASE_URL}")
    logger.info(f"API Key configured: {'Yes' if XIAOZHI_API_KEY else 'No'}")
    
    mcp.run(transport="stdio")
