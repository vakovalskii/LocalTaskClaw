"""Common data types."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str = ""
    metadata: Optional[dict] = None


@dataclass
class ToolContext:
    cwd: str
    session_id: str = ""
    history_ref: list = field(default_factory=list, repr=False)
