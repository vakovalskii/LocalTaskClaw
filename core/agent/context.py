"""Context injection — memory, workspace info."""

import os
from config import CONFIG
from logger import agent_logger


async def inject_memory(cwd: str, workspace_info: str) -> tuple[str, bool]:
    """Load MEMORY.md and inject into workspace context."""
    if not CONFIG.memory_enabled:
        return workspace_info, False

    memory_file = os.path.join(cwd, "MEMORY.md")
    overflow = False
    try:
        if os.path.exists(memory_file):
            content = open(memory_file).read().strip()
            if content and content not in ("# Agent Memory", "# Agent Memory\n\nNotes from previous sessions."):
                raw_len = len(content)
                if raw_len > CONFIG.max_memory_chars:
                    content = content[:CONFIG.max_memory_chars] + "\n...(truncated)"
                    overflow = True
                workspace_info += f"\n\n<MEMORY>\n{content}\n</MEMORY>"
                if overflow:
                    workspace_info += (
                        f"\n\n⚠️ MEMORY.md вырос до {raw_len // 1024}kb и обрезается. "
                        "Хочешь, я пересоберу его — уберу устаревшее и сожму дубли?"
                    )
                agent_logger.info(f"Memory injected: {len(content)} chars (overflow={overflow})")
    except Exception as e:
        agent_logger.warning(f"Memory load failed: {e}")

    return workspace_info, overflow
