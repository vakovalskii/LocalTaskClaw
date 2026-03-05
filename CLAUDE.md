# LocalClaw — Developer Guidelines

Personal AI agent. Single-user. Runs on any Linux server or MacBook.
Repo: https://github.com/vakovalskii/LocalClaw

---

## Project Structure

```
core/           Python ReAct agent + FastAPI
  agent/        Orchestration: run loop, session, prompt, skills, context
    run.py      Main ReAct loop — uses call_llm_stream for real token streaming
    session.py  In-memory + SQLite persistence (loads history on get)
    context.py  Bootstrap files injection (AGENTS.md, SOUL.md, USER.md, TOOLS.md, IDENTITY.md)
    skills.py   SKILL.md scanner (core/skills/, workspace/.agents/skills/)
    prompt.py   System prompt loader (system.txt)
  tools/        Tool implementations
    bash.py     run_command — security check, safe env, timeout
    web.py      search_web (Brave + DDG fallback), fetch_page (Jina reader)
    files.py    read_file, write_file, list_files, delete_file
    edit.py     edit_file (read → patch → write)
    memory.py   memory() tool — append/read MEMORY.md
    scheduler.py schedule_task()
    search.py   search_tools() — lists all registered tools incl. MCP
    mcp.py      MCP stdio transport (JSON-RPC 2.0), McpManager singleton
  skills/       Built-in skills (SKILL.md format)
  config.py     All config via env vars
  llm.py        OpenAI-compatible client: call_llm (batch) + call_llm_stream (token streaming)
  security.py   Hard-block + soft-confirm patterns, injection detection
  system.txt    Agent system prompt (persona, tools, skills, env sections)
  db.py         SQLite: sessions, messages, scheduled_tasks, agent_events
  api.py        FastAPI: /chat (SSE streaming), /history, /sessions, /events,
                /tasks, /files, /file, /settings, /logs/tail, /logs/stream

bot/            Telegram bot (single-user, OWNER_ID guard)
  main.py       Streaming bot: sendMessageDraft (Bot API 9.3+) + editMessageText fallback
                ⏳ placeholder → live draft → delete placeholder → final message

admin/          Single-file SPA admin UI (index.html)
  Pages: CHAT, SESSIONS, TASKS, FILES, LOGS, SETTINGS

install.sh      Install wizard: Docker + Native modes, Ollama picker

secrets/        Local secrets (gitignored, chmod 600)
  core.env      MODEL, LLM_BASE_URL, LLM_API_KEY, BOT_TOKEN, OWNER_ID,
                API_SECRET, WORKSPACE, DB_PATH
  bot.env       BOT_TOKEN, OWNER_ID, API_SECRET, CORE_URL
```

---

## Run Locally (Mac)

```bash
# Start core (reads secrets/core.env)
cd core
set -a && source ../secrets/core.env && set +a
python -m uvicorn api:app --host 0.0.0.0 --port 8000

# Or via venv:
.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000

# Start bot (separate terminal)
cd bot
set -a && source ../secrets/bot.env && set +a
.venv/bin/python main.py
```

Admin UI: http://localhost:8000/admin/
Health: http://localhost:8000/health

---

## Key Features

- **Token-level SSE streaming**: `llm.py::call_llm_stream` streams from LLM → `run_agent` emits per-token events → `/chat?stream=true` SSE → admin UI + bot see it live
- **Telegram streaming**: bot uses `sendMessageDraft` (Bot API 9.3+, live preview) with `editMessageText` fallback (throttle 0.8s)
- **Admin UI → Telegram relay**: messages from admin UI are forwarded to owner's Telegram via `_forward_to_telegram()` in api.py
- **History persistence**: SQLite (`messages` table), reloaded on session start — survives restarts
- **MCP support**: configure servers in `workspace/mcp_servers.json`
- **Skills**: SKILL.md scanner + `npx skills add` ecosystem
- **Security**: hard-block (fork bombs, exfil) + soft-confirm (rm -rf, DROP TABLE) + injection detection

---

## Key Files to Edit

| What | File |
|------|------|
| Agent persona / behavior | `core/system.txt` |
| New tool | `core/tools/mytool.py` → `core/tools/__init__.py` |
| Config defaults | `core/config.py` |
| Security rules | `core/security.py` |
| Context injected into prompt | `core/agent/context.py` |
| Main agent loop | `core/agent/run.py` |
| Telegram bot | `bot/main.py` |
| Admin UI | `admin/index.html` |

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

Configure in `workspace/mcp_servers.json`:
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
MCP tools appear as `mcp_{server}_{tool_name}` in the agent.

---

## Config Reference (env vars)

| Var | Default | Description |
|-----|---------|-------------|
| `MODEL` | `qwen2.5:7b` | LLM model name |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API URL |
| `LLM_API_KEY` | `ollama` | API key (use `ollama` for Ollama) |
| `BOT_TOKEN` | — | Telegram bot token (also used in core for UI→TG relay) |
| `OWNER_ID` | `0` | Telegram user ID (0 = allow all) |
| `API_SECRET` | — | Shared secret core ↔ bot ↔ admin UI |
| `WORKSPACE` | `/data/workspace` | Agent workspace directory |
| `DB_PATH` | `/data/localclaw.db` | SQLite DB path (**must exist before start**) |
| `BRAVE_API_KEY` | — | Brave Search (optional, DDG fallback if empty) |
| `MAX_ITERATIONS` | `20` | Max ReAct loop iterations per request |
| `COMMAND_TIMEOUT` | `60` | Bash command timeout (seconds) |
| `MEMORY_ENABLED` | `true` | Load MEMORY.md into context |
| `MAX_TOKENS` | `4096` | Max completion tokens |
| `CONTEXT_LIMIT` | `80000` | Token limit before history compaction |

---

## API Endpoints

```
POST /chat              { message, chat_id, stream }  — agent chat, SSE if stream=true
POST /clear             { chat_id }                   — clear session history
GET  /history           ?chat_id=                     — full conversation history
GET  /sessions                                        — list sessions
GET  /events            ?session_key=&limit=          — agent event trace
GET  /tasks                                           — list scheduled tasks
POST /tasks             { name, prompt, interval_minutes|cron }
DELETE /tasks/{id}
PATCH /tasks/{id}/toggle
GET  /files             ?path=                        — list directory
GET  /file              ?path=                        — read file
POST /file              { path, content }             — write file
DELETE /file            ?path=                        — delete file/dir
GET  /settings                                        — get settings
POST /settings          { model, llm_base_url, ... }  — update core.env
GET  /logs/tail         ?source=core|bot&lines=200    — last N log lines
GET  /logs/stream       ?source=core|bot&key=SECRET   — SSE log stream (key via query param)
GET  /health                                          — status check
```

---

## Coding Style

- Python 3.12+, async/await everywhere
- All tools: `async def tool_*(args: dict, ctx: ToolContext) -> ToolResult`
- No external databases — SQLite only, no Redis/Postgres
- No secrets in code — env vars only (secrets/ dir gitignored)
- Keep files under ~300 LOC; split if larger
- Brief comments for non-obvious logic

---

## Roadmap

```
v0.1 Foundation ✓
  [x] install.sh wizard (Docker + Native modes, Ollama)
  [x] Core ReAct agent (run loop, sessions, SQLite)
  [x] Token-level SSE streaming (call_llm_stream)
  [x] Tools: bash, web, files, edit, memory, scheduler, search_tools
  [x] MCP subprocess stdio transport
  [x] Skills system (SKILL.md scanner + npx ecosystem)
  [x] Security: hard-block + soft-confirm + injection detection
  [x] Telegram bot: sendMessageDraft streaming (Bot API 9.3+)
  [x] Admin UI: Chat, Sessions, Tasks, Files, Logs, Settings
  [x] Admin UI → Telegram relay (responses forwarded to owner)
  [x] History persistence across restarts

v0.2 Polish
  [ ] Vision (multimodal — images in Telegram)
  [ ] Voice messages (Whisper ASR)
  [ ] install.sh: Native mode launchd/systemd process management
  [ ] Chat UI: load history on open ✓ (done)

v0.3 Multi-channel
  [ ] WhatsApp (unofficial or official API)
  [ ] Web chat widget for embedding

v0.4 Plugins
  [ ] Self-update
  [ ] Google Workspace MCP
```
