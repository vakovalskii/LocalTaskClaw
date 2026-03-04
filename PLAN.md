# LocalClaw — Plan

Personal AI agent. Single-user. Runs on any Linux server or MacBook.

## Core idea

- 3-step install on any Linux/macOS (curl | bash)
- Single-user, no corporate bloat
- Any OpenAI-compatible model OR Ollama (local, auto-install)
- Telegram bot as primary interface
- Simple admin UI (5 pages, not a SaaS dashboard)
- Secure by default
- Two modes: Docker (server) or Native (MacBook/laptop, no Docker needed)

---

## Two install modes

### Mode 1 — Docker (recommended for servers)
- Full isolation via containers
- HTTPS via Let's Encrypt (with domain) or IP:port (without)
- 4 containers: core, bot, admin, postgres + optional traefik
- Secrets in files with chmod 600
- `docker compose up -d`

### Mode 2 — Native (MacBook / laptop / no Docker)
- No Docker required
- Python venv in `~/.localclaw/`
- Processes managed via launchd (macOS) or systemd (Linux)
- Secrets in `~/.localclaw/secrets/` chmod 600
- Isolation: agent runs bash in subprocess with restricted env
- Start/stop: `localclaw start` / `localclaw stop`
- Storage: SQLite (no postgres needed)
- Same Ollama integration

---

## Install wizard flow (install.sh)

```
Step 1 — Pre-checks        docker/compose OR python3/pip/venv
Step 2 — Install mode      Docker vs Native
Step 3 — Network           domain (HTTPS) vs IP:port vs localhost (native)
Step 4 — Telegram          paste token → /start → capture owner ID
Step 5 — Access policy     DM only vs groups
Step 6 — Models            Ollama (auto RAM/VRAM detect + model picker)
                           OR external API (URL + key + model name)
Step 7 — Web search        Brave API key (optional, fallback = DuckDuckGo)
Step 8 — Review & confirm
Step 9 — Install & start
Step 10 — Print URL + password
```

### Ollama model picker (by available RAM/VRAM)
| RAM    | Model           | Size  | Notes                        |
|--------|-----------------|-------|------------------------------|
| 4GB    | qwen2.5:3b      | 2.0GB | minimum, basic tool use      |
| 8GB    | qwen2.5:7b      | 4.7GB | ★ best under 8GB, great tools|
| 12GB   | qwen2.5:14b     | 9.0GB | ★★ top under 16GB            |
| 24GB   | qwen2.5:32b     | 19GB  | ★★★ best under 32GB          |
| 24GB   | deepseek-r1:14b | 9.0GB | reasoning model              |
| 48GB+  | qwen2.5:72b     | 47GB  | top open-source              |

---

## Architecture

### What we strip from DaisyMobile
**Keep:**
- `core/` — Python ReAct agent (agent/run.py, session.py, prompt.py, context.py)
- `core/tools/` — bash, web, files, mcp, memory, scheduler, vision, sandbox, send_telegram
- `bot/` — Telegram bot (single-user, stripped)
- `admin/` — React UI (heavily simplified, see below)

**Remove:**
- LiveKit + egress + Redis (voice/video)
- MinIO → plain /data volume or local filesystem
- userbot (Telethon)
- auth-bot (web/mobile auth)
- btrxclaw-frontend (Next.js)
- adminer
- google-workspace-mcp (future plugin)
- Bitrix24 tools (bitrix24_rest.py, bitrixclaw_api.py)
- subscription.py, usage.py (billing)
- multi-user auth, JWT web clients
- all corporate/team features

---

## System prompt (system.txt)

Best ideas from DaisyMobile + OpenClaw combined:

```
<CORE_PRINCIPLE>
  Anti-hallucination: tool call MUST be in SAME response.
  Never say "I'll search..." without calling the tool.

<PERSONA>
  Conversational, casual Russian/English.
  BAD/GOOD examples to enforce style.
  No markdown lists — flowing text in messenger style.

<SECURITY>
  Injection vectors (from DaisyMobile's detailed list).
  Exfiltration patterns, base64 attack, prompt injection.
  Condensed — not full 39K char version.

<ENVIRONMENT>
  {{cwd}}, {{date}}, {{ports}}, sandbox info.
  Time reasoning rules (night/morning/tomorrow logic).

<TOOLS>
  Dynamic from available tools.
  search_tools(query=) discovery pattern.
  schedule_task vs plan distinction.

<SKILLS>
  npx skills ecosystem + builtin skills.

<SCHEDULED_TASKS>
  Silence filter: only send if genuinely important.
  Routine/spam → stay silent.
```

---

## Admin UI (simplified — 5 pages)

### Keep
- `/` — Chat (main, talk to agent)
- `/sessions` — Session history + agent trace viewer
- `/tasks` — Scheduled tasks (view/cancel)
- `/files` — Workspace file browser
- `/settings` — Model, bot token, language, memory, Brave key, heartbeat

### Remove from DaisyMobile admin
- User management / multi-user
- Subscription / billing / usage caps
- Invite links / access codes
- Organization / team settings
- Google OAuth panel (future plugin)
- Bitrix24 integration panel
- LiveKit / voice call UI
- Mobile app deep links
- Analytics dashboard
- Notification feed

### Steal from OpenClaw
- Session .jsonl trace viewer (see every tool call)
- Compaction config (reserve tokens, mode)
- Model aliases / selector per session
- Heartbeat config (every X min, active hours, prompt)

---

## Web search

- Primary: Brave Search API (user provides key)
- Fallback: DuckDuckGo scrape (no key, slower)
- Future: Tavily, Perplexity as options in settings
- Tool: tools/web.py → search_web(query, limit=5)

---

## Security

**Docker mode:**
- JWT secret + admin password auto-generated
- All secrets: files chmod 600
- Internal services on bridge network
- Only Traefik exposes 80/443

**Native mode:**
- Secrets in ~/.localclaw/secrets/ chmod 600
- Agent subprocess with restricted env (no secrets leak)
- Workspace isolated to ~/.localclaw/workspace/
- Admin panel: localhost only + password

---

## Roadmap

### v0.1 — Foundation (NOW)
- [x] install.sh wizard base
- [x] Ollama: RAM detect, model picker, auto-install
- [ ] install.sh: Docker vs Native mode choice
- [ ] Stripped docker-compose.yml (4 containers)
- [ ] Native mode: launchd (macOS) / systemd (Linux) process manager
- [ ] Core agent: Python ReAct stripped from DaisyMobile
- [ ] Telegram bot: single-user, stripped
- [ ] system.txt: combined best of DaisyMobile + OpenClaw
- [ ] Brave Search tool

### v0.2 — Admin UI
- [ ] Chat interface
- [ ] Session viewer with agent trace
- [ ] Task manager
- [ ] Settings page

### v0.3 — Tools & Skills
- [ ] MCP support
- [ ] Skills system (npx ecosystem)
- [ ] Vision (multimodal)
- [ ] Memory (MEMORY.md)

### v0.4 — Plugins
- [ ] Google Workspace
- [ ] Voice messages (Whisper ASR)
- [ ] Self-update
