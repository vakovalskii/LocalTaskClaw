# LocalTaskClaw

Personal AI agent controllable via Telegram and a Web Admin UI. Built around a ReAct agent loop with FastAPI, SQLite persistence, real token streaming, a multi-agent kanban board, and MCP server support. Works with any OpenAI-compatible model (local via Ollama or cloud).

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/vakovalskii/LocalTaskClaw/main/install.sh | bash
```

The interactive wizard walks through mode selection, Telegram bot setup, model choice, and service registration. Takes about 5 minutes.

## Features

- **Telegram bot** with live typing preview (Bot API 9.3+ `sendMessageDraft`, `editMessageText` fallback)
- **Admin UI** (SPA) -- chat, sessions, kanban board, tasks, files, logs, settings
- **Kanban board** -- 5-column board (Backlog / In Progress / Review / Done / Needs Human), up to 10 agents with custom identities and roles
- **Orchestrator / Worker model** -- orchestrator agents dispatch workers via `kanban_run`, read artifacts via `kanban_read_result`, verify via `kanban_verify`, send reports via `kanban_report`
- **Auto-retry** -- rejected tasks retry up to 2 times, then escalate to Needs Human
- **Repeat / heartbeat** -- tasks with `repeat_minutes > 0` auto-rerun on schedule
- **Parallel tool calls** -- agents run multiple tools concurrently via `asyncio.gather`
- **Real token streaming** -- SSE streaming in both Admin UI and Telegram
- **Web search** via DuckDuckGo (Brave API optional)
- **MCP servers** -- extend the agent with any Model Context Protocol tool
- **Skills system** -- SKILL.md scanner + `npx skills add` ecosystem
- **Security** -- hard-block (fork bombs, exfil), soft-confirm (rm -rf, DROP TABLE), injection detection
- **Any OpenAI-compatible model** -- Ollama (local) or cloud API

## Architecture

```
core/           Python ReAct agent + FastAPI + SQLite
bot/            Telegram bot (single-user, OWNER_ID guard)
admin/          Single-file SPA admin UI (index.html)
scripts/        Utilities (seed_kanban.py)
tests/          End-to-end integration tests
```

| Component | Role |
|-----------|------|
| **Core** | ReAct agent loop, FastAPI REST + SSE API, SQLite persistence, tool execution, MCP transport |
| **Bot** | Telegram long-polling bot with streaming replies, owner-only access |
| **Admin UI** | Browser-based SPA -- chat, sessions, kanban, scheduled tasks, file browser, log viewer, settings |
| **Traefik** | HTTPS reverse proxy (optional, Docker mode with a domain) |

The Core listens on port **11387** by default. The Bot connects to Core over HTTP. The Admin UI is served by Core at `/admin`.

## Installation Modes

The installer offers three isolation levels:

### 1. Docker (recommended for servers)

Agent runs inside containers. Access is limited to a dedicated volume. Requires Docker and Docker Compose.

### 2. Native processes

Agent runs as a Python process directly on the host. Full filesystem access. Requires Python 3.12+, git, pip.

### 3. Restricted (sandboxed)

Same as native, but the agent is confined to `~/.localtaskclaw/workspace`. File tools cannot escape the workspace directory.

## Scripts

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/vakovalskii/LocalTaskClaw/main/install.sh | bash
```

The wizard prompts for:
- Installation mode (Docker / Native / Restricted)
- Telegram bot token (validated live against the Bot API)
- Owner Telegram ID (auto-detected via `/start` or entered manually)
- LLM provider (Ollama with hardware-aware model picker, or external OpenAI-compatible API)

After completion it registers system services and performs a health check.

### Update

```bash
bash ~/.localtaskclaw/app/update.sh
```

Pulls the latest code via git, reinstalls dependencies if `requirements.txt` changed, and restarts services. Supports `--quiet` flag for headless execution (called from API).

### Uninstall

```bash
bash ~/.localtaskclaw/app/uninstall.sh
```

Stops services, removes LaunchAgents/systemd units, deletes `~/.localtaskclaw` (code, venv, database, secrets, workspace), and cleans up log files. Prompts for confirmation before proceeding.

### Demo Kanban Board

Seed the board with 4 specialist worker agents, 1 orchestrator, and 5 demo tasks:

```bash
~/.localtaskclaw/venv/bin/python ~/.localtaskclaw/app/scripts/seed_kanban.py
```

Reset all existing data and re-seed from scratch:

```bash
~/.localtaskclaw/venv/bin/python ~/.localtaskclaw/app/scripts/seed_kanban.py --reset
```

Print current board state without changes:

```bash
~/.localtaskclaw/venv/bin/python ~/.localtaskclaw/app/scripts/seed_kanban.py --status
```

The script reads `API_SECRET` from `secrets/core.env` automatically. Override the API URL with the `API_URL` environment variable if needed.

### Run Tests

Integration tests run against the live service at `localhost:11387`.

Kanban CRUD, tool execution, worker/orchestrator lifecycle:

```bash
~/.localtaskclaw/venv/bin/pytest ~/.localtaskclaw/app/tests/test_kanban_e2e.py -v -s
```

Seed pipeline validation (runs `seed_kanban.py --reset` first, then verifies structure and orchestration):

```bash
~/.localtaskclaw/venv/bin/pytest ~/.localtaskclaw/app/tests/test_seed_e2e.py -v -s
```

## Service Management

### macOS (launchctl)

```bash
# Start
launchctl load ~/Library/LaunchAgents/io.localtaskclaw.core.plist
launchctl load ~/Library/LaunchAgents/io.localtaskclaw.bot.plist

# Stop
launchctl unload ~/Library/LaunchAgents/io.localtaskclaw.core.plist
launchctl unload ~/Library/LaunchAgents/io.localtaskclaw.bot.plist

# Logs
tail -f /tmp/localtaskclaw-core.log
tail -f /tmp/localtaskclaw-bot.log
```

Services are registered as LaunchAgents and start automatically on login.

### Linux (systemd)

```bash
# Start
systemctl --user start localtaskclaw-core localtaskclaw-bot

# Stop
systemctl --user stop localtaskclaw-core localtaskclaw-bot

# Status
systemctl --user status localtaskclaw-core localtaskclaw-bot

# Enable on boot
systemctl --user enable localtaskclaw-core localtaskclaw-bot

# Logs
tail -f /tmp/localtaskclaw-core.log
tail -f /tmp/localtaskclaw-bot.log
```

### Docker

```bash
# Start
docker compose -f ~/localtaskclaw/docker-compose.yml up -d

# Stop
docker compose -f ~/localtaskclaw/docker-compose.yml down

# Status
docker compose -f ~/localtaskclaw/docker-compose.yml ps

# Logs
docker compose -f ~/localtaskclaw/docker-compose.yml logs -f

# Update images
docker compose -f ~/localtaskclaw/docker-compose.yml pull && \
docker compose -f ~/localtaskclaw/docker-compose.yml up -d
```

## Admin UI

- **URL**: `http://localhost:11387/admin`
- **Login**: use the `API_SECRET` value from `secrets/core.env` as password

Pages:

| Page | Description |
|------|-------------|
| **Chat** | Conversational interface with real-time token streaming |
| **Sessions** | Browse and resume past conversations |
| **Kanban** | Multi-agent task board with drag-and-drop, run/cancel/verify controls |
| **Tasks** | Scheduled tasks (cron or interval-based) |
| **Files** | Workspace file browser with read/write/delete |
| **Logs** | Live-streamed core and bot logs |
| **Settings** | Change model, LLM URL, API keys, and other config at runtime |

Messages sent through the Admin UI are also forwarded to the owner's Telegram chat.

## API Endpoints

All endpoints require the `X-Api-Key` header set to `API_SECRET` (except `/health`).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Agent chat (set `stream=true` for SSE token streaming) |
| `POST` | `/clear` | Clear session history |
| `GET` | `/history` | Full conversation history (`?chat_id=`) |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/events` | Agent event trace (`?session_key=&limit=`) |
| `GET` | `/tasks` | List scheduled tasks |
| `POST` | `/tasks` | Create scheduled task (`name`, `prompt`, `interval_minutes` or `cron`) |
| `DELETE` | `/tasks/{id}` | Delete scheduled task |
| `PATCH` | `/tasks/{id}/toggle` | Enable/disable scheduled task |
| `GET` | `/files` | List workspace directory (`?path=`) |
| `GET` | `/file` | Read file contents (`?path=`) |
| `POST` | `/file` | Write file (`path`, `content`) |
| `DELETE` | `/file` | Delete file or directory (`?path=`) |
| `GET` | `/settings` | Get current settings |
| `POST` | `/settings` | Update settings (writes to `core.env`) |
| `GET` | `/logs/tail` | Last N log lines (`?source=core\|bot&lines=200`) |
| `GET` | `/logs/stream` | SSE log stream (`?source=core\|bot&key=SECRET`) |
| `GET` | `/health` | Health check (no auth required) |
| `GET` | `/agents` | List kanban agents |
| `POST` | `/agents` | Create agent |
| `DELETE` | `/agents/{id}` | Delete agent |
| `GET` | `/kanban` | List all kanban tasks |
| `POST` | `/kanban/tasks` | Create kanban task |
| `PATCH` | `/kanban/tasks/{id}` | Update task fields |
| `DELETE` | `/kanban/tasks/{id}` | Delete task |
| `POST` | `/kanban/tasks/{id}/move` | Move task to column |
| `POST` | `/kanban/tasks/{id}/run` | Start agent execution on task |
| `POST` | `/kanban/tasks/{id}/cancel` | Cancel running task |

## Configuration

Environment variables are stored in `secrets/core.env` (native/restricted) or passed via Docker environment.

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `qwen2.5:7b` | LLM model name |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API URL |
| `LLM_API_KEY` | `ollama` | API key (`ollama` for local Ollama) |
| `BOT_TOKEN` | -- | Telegram bot token from @BotFather |
| `OWNER_ID` | `0` | Telegram user ID (0 = allow all) |
| `API_SECRET` | -- | Shared secret for core, bot, and admin UI auth |
| `WORKSPACE` | `/data/workspace` | Agent workspace directory |
| `DB_PATH` | `/data/localtaskclaw.db` | SQLite database path |
| `BRAVE_API_KEY` | -- | Brave Search API key (optional, DuckDuckGo fallback) |
| `MAX_ITERATIONS` | `20` | Max ReAct loop iterations per request |
| `COMMAND_TIMEOUT` | `60` | Bash command timeout in seconds |
| `MAX_TOKENS` | `4096` | Max completion tokens per LLM call |
| `CONTEXT_LIMIT` | `80000` | Token limit before history compaction |
| `MEMORY_ENABLED` | `true` | Load MEMORY.md into agent context |
| `API_PORT` | `11387` | Port for the FastAPI server |

## MCP Servers

Configure external MCP tool servers in `workspace/mcp_servers.json`:

```json
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "ghp_..." }
    }
  }
}
```

MCP tools are auto-discovered and appear as `mcp_{server}_{tool_name}` in the agent's tool list. The agent communicates with MCP servers via stdio JSON-RPC 2.0 transport.

## License

MIT
