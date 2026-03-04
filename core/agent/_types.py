"""Agent data types."""

from dataclasses import dataclass, field


@dataclass
class AgentResult:
    text: str
    tool_events: list  # [{"name": str, "args": dict, "result": str, "success": bool}]
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    def __str__(self) -> str:
        return self.text


@dataclass
class Session:
    session_key: str
    cwd: str
    history: list = field(default_factory=list)
