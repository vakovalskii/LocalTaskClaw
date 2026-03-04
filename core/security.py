"""Security checks for tool execution.

Principles:
1. Destructive actions (delete, overwrite, mass operations) require explicit confirmation
2. Block path traversal outside workspace
3. Block dangerous shell patterns
4. Never leak secrets (env vars, key files)
"""

import re
import os
from dataclasses import dataclass


# ── Dangerous shell patterns (always blocked, no confirmation) ────────────────

_HARD_BLOCK = [
    (r"\brm\s+-[^\s]*r[^\s]*\s+/", "recursive delete from root"),
    (r":\s*\(\s*\)\s*\{.*fork", "fork bomb"),
    (r">\s*/dev/sd[a-z]", "overwrite block device"),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bshred\b.*--force", "shred with force"),
    (r"curl\s+.*\|\s*(ba)?sh", "pipe to shell from network"),
    (r"wget\s+.*\|\s*(ba)?sh", "pipe to shell from network"),
    (r"base64\s+-d.*\|\s*(ba)?sh", "execute base64-encoded payload"),
    (r"\bchmod\s+[0-7]*7[0-7]*\s+/\b", "chmod 777 on root"),
    (r"\biptables\s+-F\b", "flush firewall rules"),
    (r"\bsystemctl\s+(stop|disable)\s+", "stop/disable system service"),
    # Exfiltration patterns
    (r"curl\s+.*\$\w+", "potential secret exfiltration via curl"),
    (r"wget\s+.*\$\w+", "potential secret exfiltration via wget"),
]

_HARD_BLOCK_RE = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _HARD_BLOCK]


# ── Destructive actions that require confirmation ─────────────────────────────

_NEEDS_CONFIRM = [
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\brm\s+-f", "forced delete"),
    (r"\bdd\b.*if=", "disk copy"),
    (r"\btruncate\b", "file truncate"),
    (r"\bkill\s+-9\b", "force kill process"),
    (r"\bkillall\b", "kill all processes"),
    (r"\bdropdb\b", "drop database"),
    (r"\bdrop\s+table\b", "drop table"),
    (r"\bDELETE\s+FROM\b", "mass delete from database"),
    (r"\bUPDATE\s+\w+\s+SET\b(?!.*WHERE)", "update without WHERE clause"),
    (r"\bgit\s+push\s+.*--force\b", "force push"),
    (r"\bgit\s+reset\s+--hard\b", "hard git reset"),
    (r"\bgit\s+clean\s+-[^\s]*f", "git clean force"),
    (r"\bnpm\s+publish\b", "npm publish"),
    (r"\bpip\s+uninstall\b", "pip uninstall"),
]

_NEEDS_CONFIRM_RE = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _NEEDS_CONFIRM]


# ── Secret files — block reading these unless workspace-relative ──────────────

_SECRET_FILE_PATTERNS = [
    r"\.env$",
    r"secrets?/",
    r"id_rsa",
    r"id_ed25519",
    r"\.pem$",
    r"\.key$",
    r"credentials",
    r"\.ssh/",
]
_SECRET_FILE_RE = [re.compile(p, re.IGNORECASE) for p in _SECRET_FILE_PATTERNS]


@dataclass
class SecurityCheck:
    blocked: bool = False       # Hard block — refuse
    needs_confirm: bool = False  # Soft — ask user before executing
    reason: str = ""


def check_command(command: str) -> SecurityCheck:
    """Check a shell command for security issues."""
    # Hard blocks first
    for pattern, reason in _HARD_BLOCK_RE:
        if pattern.search(command):
            return SecurityCheck(blocked=True, reason=f"Blocked: {reason}")

    # Needs confirmation
    for pattern, reason in _NEEDS_CONFIRM_RE:
        if pattern.search(command):
            return SecurityCheck(needs_confirm=True, reason=reason)

    return SecurityCheck()


def check_file_access(path: str, workspace: str) -> SecurityCheck:
    """Check if file access is safe."""
    resolved = os.path.realpath(path)
    ws = os.path.realpath(workspace)

    # Block access outside workspace to secret files
    if not resolved.startswith(ws):
        for pattern in _SECRET_FILE_RE:
            if pattern.search(path):
                return SecurityCheck(
                    blocked=True,
                    reason=f"Blocked: reading secret file outside workspace ({path})"
                )

    return SecurityCheck()


def sanitize_output(output: str) -> str:
    """Remove potential secrets from tool output before sending to LLM."""
    # Redact anything that looks like an API key or token
    output = re.sub(
        r'(api[_-]?key|token|secret|password|passwd|credential)\s*[=:]\s*\S+',
        r'\1=***REDACTED***',
        output,
        flags=re.IGNORECASE,
    )
    return output


def check_for_injection(content: str) -> bool:
    """Check fetched content for prompt injection attempts."""
    injection_patterns = [
        r"ignore (previous|all|your) instructions",
        r"you are now",
        r"system:\s*",
        r"<\s*/?system\s*>",
        r"forget (everything|your instructions)",
        r"new (instructions|persona|role)",
        r"disregard your",
        r"override (your )?instructions",
    ]
    for p in injection_patterns:
        if re.search(p, content, re.IGNORECASE):
            return True
    return False
