# LocalClaw — Developer Guidelines

Personal AI agent. Single-user. Runs on any Linux server or MacBook.
Repo: https://github.com/vakovalskii/LocalClaw

---

## Project Structure

```
core/           Python ReAct agent + FastAPI
  agent/        Orchestration: run loop, session, prompt, skills, context
  tools/        Tool implementations: bash, web, files, edit, memory, scheduler, mcp, search_tools
  skills/       Built-in skills (SKILL.md format, copied from openclaw)
  config.py     All config via env vars
  security.py   Hard-block + soft-confirm patterns, injection detection
  system.txt    Agent system prompt (edit this to change agent behavior)
  db.py         SQLite: sessions, messages, scheduled_tasks, agent_events

bot/            Telegram bot (single-user, OWNER_ID guard)

install.sh      Install wizard: Docker + Native modes, Ollama picker

secrets-template/   Copy → secrets/, fill in, chmod 600
config-template/    mcp_servers.json example
```

---

## Run Locally (development)

```bash
# Core agent
cd core
pip install -r requirements.txt
MODEL=qwen2.5:7b LLM_BASE_URL=http://localhost:11434/v1 \
  API_SECRET=dev OWNER_ID=0 WORKSPACE=/tmp/lc-workspace \
  python main.py

# Bot (separate terminal)
cd bot
pip install -r requirements.txt
BOT_TOKEN=... OWNER_ID=... API_SECRET=dev CORE_URL=http://localhost:8000 \
  python main.py
```

## Docker

```bash
# Fill in secrets first
cp secrets-template/core.env secrets/core.env
cp secrets-template/bot.env  secrets/bot.env
chmod 600 secrets/*.env
# Edit secrets/*.env with your values

docker compose up -d --build
docker compose logs -f
```

---

## Key Files to Edit

| What you want to change | File |
|-------------------------|------|
| Agent behavior / persona | `core/system.txt` |
| New tool | `core/tools/mytool.py` → register in `core/tools/__init__.py` |
| Config vars / defaults | `core/config.py` |
| Security rules | `core/security.py` |
| Context injected into prompt | `core/agent/context.py` |
| Main agent loop | `core/agent/run.py` |
| Telegram bot behavior | `bot/main.py` |

---

## Adding a Tool

1. Create `core/tools/mytool.py`:
   ```python
   from models import ToolResult, ToolContext

   async def tool_my_thing(args: dict, ctx: ToolContext) -> ToolResult:
       ...
       return ToolResult(True, output="result")

   TOOL_DEFINITION = {
       "type": "function",
       "function": {
           "name": "my_thing",
           "description": "...",
           "parameters": {"type": "object", "properties": {...}},
       },
   }
   ```

2. Register in `core/tools/__init__.py`:
   ```python
   from tools.mytool import tool_my_thing, TOOL_DEFINITION as MYTOOL_DEF
   _BUILTIN_HANDLERS["my_thing"] = tool_my_thing
   _DEFINITIONS.append(MYTOOL_DEF)
   ```

---

## MCP Servers

Configure in `workspace/mcp_servers.json` (or `/data/mcp_servers.json` in Docker):
```json
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "ghp_..."}
    }
  }
}
```
See `config-template/mcp_servers.json` for more examples.
MCP tools appear as `mcp_{server}_{tool_name}` in the agent.

---

## Skills (npx ecosystem)

Built-in skills live in `core/skills/` (github, weather, tmux, coding-agent, nano-pdf, openai-whisper-api).

User can install more via agent:
```
run_command("npx skills add vercel-labs/skills@deep-research -y")
```
Skills install to `workspace/.agents/skills/` and load automatically on next message.

---

## Security

`core/security.py` has two tiers:

- **Hard block** (refuse silently): fork bombs, `rm -rf /`, `mkfs`, pipe-to-shell from network, base64→bash payloads, exfiltration patterns
- **Soft confirm** (ask user): `rm -rf <dir>`, `git reset --hard`, `kill -9`, `npm publish`, `DROP TABLE`, `DELETE FROM` without WHERE

Prompt injection detection in `fetch_page` — warns agent when fetched content looks suspicious.

File path traversal blocked in `tools/files.py` and `tools/edit.py` — paths outside workspace are rejected.

---

## Config Reference (env vars)

| Var | Default | Description |
|-----|---------|-------------|
| `MODEL` | `qwen2.5:7b` | LLM model name |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API URL |
| `LLM_API_KEY` | `ollama` | API key |
| `BOT_TOKEN` | — | Telegram bot token |
| `OWNER_ID` | `0` | Telegram user ID (0 = allow all) |
| `API_SECRET` | — | Shared secret between core ↔ bot |
| `WORKSPACE` | `/data/workspace` | Agent workspace directory |
| `DB_PATH` | `/data/localclaw.db` | SQLite database path |
| `BRAVE_API_KEY` | — | Brave Search (optional, DDG fallback) |
| `MAX_ITERATIONS` | `20` | Max agent loop iterations |
| `COMMAND_TIMEOUT` | `60` | Bash command timeout (seconds) |
| `MEMORY_ENABLED` | `true` | Load MEMORY.md into context |

---

## Coding Style

- Python 3.12+, async/await everywhere
- All tools are `async def tool_*(args: dict, ctx: ToolContext) -> ToolResult`
- No external databases — SQLite only
- No secrets in code — env vars only
- Keep files under ~300 LOC; split if larger
- Brief comments for non-obvious logic

---

## Roadmap

```
v0.1 Foundation (current)
  [x] install.sh wizard (Docker + Native modes, Ollama)
  [x] Core ReAct agent (run loop, sessions, SQLite)
  [x] Tools: bash, web, files, edit, memory, scheduler, search_tools
  [x] MCP subprocess stdio transport
  [x] Skills system (SKILL.md scanner + npx ecosystem)
  [x] Security: hard-block + soft-confirm + injection detection
  [x] Telegram bot (single-user, OWNER_ID guard)
  [ ] install.sh: Native mode launchd/systemd process management
  [ ] system.txt: finalize and test with Ollama models

v0.2 Admin UI
  [ ] Chat interface (web)
  [ ] Session viewer with agent trace (tool events)
  [ ] Scheduled tasks manager
  [ ] Settings page (model, bot token, memory, Brave key)

v0.3 Tools & Skills
  [ ] Vision (multimodal — images in Telegram)
  [ ] Voice messages (Whisper ASR)
  [ ] More default skills

v0.4 Plugins
  [ ] Self-update
  [ ] Google Workspace MCP
```
