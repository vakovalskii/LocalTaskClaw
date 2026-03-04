"""Context injection — workspace bootstrap files, memory, daily notes."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from config import CONFIG
from logger import agent_logger


# Bootstrap files loaded into context on every session (in priority order)
_BOOTSTRAP_FILES = [
    "AGENTS.md",    # Workspace instructions for the agent
    "SOUL.md",      # Who the agent is — personality, values
    "USER.md",      # Who the user is — profile, preferences
    "TOOLS.md",     # Local setup notes — devices, hosts, env specifics
    "IDENTITY.md",  # Agent name, emoji, vibe
]

# Files loaded only when they exist (not required)
_OPTIONAL_FILES = [
    "BOOTSTRAP.md",   # First-run ritual — agent deletes after reading
    "HEARTBEAT.md",   # Scheduled task prompts
]


def seed_workspace(cwd: str):
    """Copy default workspace files if they don't exist yet (first run)."""
    defaults_dir = Path(__file__).parent.parent / "workspace-defaults"
    if not defaults_dir.exists():
        return

    seeded = []
    for fname in list(_BOOTSTRAP_FILES) + list(_OPTIONAL_FILES):
        dest = os.path.join(cwd, fname)
        src = defaults_dir / fname
        if not os.path.exists(dest) and src.exists():
            with open(src) as f:
                content = f.read()
            with open(dest, "w") as f:
                f.write(content)
            seeded.append(fname)

    if seeded:
        agent_logger.info(f"Workspace seeded: {seeded}")


def _read_file_safe(path: str, max_chars: int = 4000) -> str | None:
    try:
        if os.path.exists(path):
            content = open(path, errors="replace").read().strip()
            if content:
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n...(truncated)"
                return content
    except Exception as e:
        agent_logger.warning(f"Failed to read {path}: {e}")
    return None


async def inject_bootstrap_files(cwd: str, workspace_info: str) -> str:
    """Inject AGENTS.md, SOUL.md, USER.md, TOOLS.md, IDENTITY.md into context."""
    injected = []

    for fname in _BOOTSTRAP_FILES:
        path = os.path.join(cwd, fname)
        content = _read_file_safe(path)
        if content:
            # Skip template placeholders that haven't been filled
            if "_Fill this in_" in content or "_(fill" in content.lower():
                continue
            workspace_info += f"\n\n<{fname.replace('.md', '')}>\n{content}\n</{fname.replace('.md', '')}>"
            injected.append(fname)

    # BOOTSTRAP.md — if present, always inject (first-run)
    bootstrap_path = os.path.join(cwd, "BOOTSTRAP.md")
    if os.path.exists(bootstrap_path):
        content = _read_file_safe(bootstrap_path)
        if content:
            workspace_info += f"\n\n<BOOTSTRAP>\n{content}\n</BOOTSTRAP>"
            workspace_info += "\n\n⚠️ BOOTSTRAP.md exists — this is likely a fresh workspace. Read it and follow the first-run ritual."
            injected.append("BOOTSTRAP.md")

    if injected:
        agent_logger.info(f"Bootstrap files injected: {injected}")

    return workspace_info


async def inject_daily_memory(cwd: str, workspace_info: str) -> str:
    """Inject today's and yesterday's memory notes from memory/ directory."""
    memory_dir = os.path.join(cwd, "memory")
    if not os.path.isdir(memory_dir):
        return workspace_info

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    dates = [today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")]

    for date_str in dates:
        path = os.path.join(memory_dir, f"{date_str}.md")
        content = _read_file_safe(path, max_chars=3000)
        if content:
            label = "TODAY" if date_str == dates[0] else "YESTERDAY"
            workspace_info += f"\n\n<DAILY_MEMORY_{label} date={date_str}>\n{content}\n</DAILY_MEMORY_{label}>"
            agent_logger.info(f"Daily memory injected: {date_str}")

    return workspace_info


async def inject_memory(cwd: str, workspace_info: str) -> tuple[str, bool]:
    """Load MEMORY.md (long-term curated memory) and inject into context."""
    if not CONFIG.memory_enabled:
        return workspace_info, False

    memory_file = os.path.join(cwd, "MEMORY.md")
    overflow = False
    content = _read_file_safe(memory_file, max_chars=CONFIG.max_memory_chars + 200)

    if content:
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
        agent_logger.info(f"MEMORY.md injected: {len(content)} chars (overflow={overflow})")

    return workspace_info, overflow
