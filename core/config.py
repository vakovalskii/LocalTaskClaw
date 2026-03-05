"""LocalTaskClaw configuration — loaded from environment variables."""

import os
from dataclasses import dataclass, field

# Load env file if ENV_FILE is set (LaunchAgent / systemd pass path this way)
_env_file = os.environ.get("ENV_FILE", "")
if _env_file and os.path.isfile(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


@dataclass
class Config:
    # LLM
    model: str = field(default_factory=lambda: _env("MODEL", "qwen2.5:7b"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "http://localhost:11434/v1"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "ollama"))
    max_iterations: int = field(default_factory=lambda: _env_int("MAX_ITERATIONS", 20))
    max_tokens: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 4096))
    temperature: float = field(default_factory=lambda: float(_env("TEMPERATURE", "0.7")))

    # Telegram
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN"))
    owner_id: int = field(default_factory=lambda: _env_int("OWNER_ID", 0))

    # Paths
    workspace: str = field(default_factory=lambda: _env("WORKSPACE", "/data/workspace"))
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "/data/localtaskclaw.db"))

    # API
    api_port: int = field(default_factory=lambda: _env_int("API_PORT", 11387))
    api_secret: str = field(default_factory=lambda: _env("API_SECRET", ""))

    # Features
    brave_api_key: str = field(default_factory=lambda: _env("BRAVE_API_KEY", ""))
    memory_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_ENABLED", True))
    max_memory_chars: int = field(default_factory=lambda: _env_int("MAX_MEMORY_CHARS", 8000))

    # Limits
    command_timeout: int = field(default_factory=lambda: _env_int("COMMAND_TIMEOUT", 60))
    max_tool_output: int = field(default_factory=lambda: _env_int("MAX_TOOL_OUTPUT", 8000))
    context_limit: int = field(default_factory=lambda: _env_int("CONTEXT_LIMIT", 80000))

    # Admin UI
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD", ""))
    admin_port: int = field(default_factory=lambda: _env_int("ADMIN_PORT", 3000))


CONFIG = Config()
