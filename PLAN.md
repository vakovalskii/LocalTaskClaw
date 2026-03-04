# SimpleClaw — Plan

Personal AI agent platform. Single-user. Deploys in 3 steps on any Linux server.

## Goals

- 3-step install on any Linux server (curl | bash)
- Single-user, no corporate bloat
- Any OpenAI-compatible model (local or cloud)
- Telegram bot as primary interface
- Simple admin UI (not a SaaS dashboard)
- Secure by default (HTTPS via Let's Encrypt if domain, otherwise IP:port)
- Docker-based, 4 containers max

---

## Architecture

### What we keep from DaisyMobile
- `core/` — Python ReAct agent loop (agent/run.py, agent/session.py, agent/prompt.py)
- `core/tools/` — bash, web search, files, mcp, scheduler, vision, memory, sandbox
- `bot/` — Telegram bot (stripped, single-user)
- `admin/` — React UI (heavily simplified, see below)

### What we throw out
- LiveKit + livekit-egress + Redis (voice/video calls)
- MinIO → plain /data volume
- userbot (Telethon)
- auth-bot (web/mobile auth)
- btrxclaw-frontend (Next.js web client)
- adminer
- google-workspace-mcp (optional plugin later)
- Bitrix24 tools
- subscription.py, usage.py (billing)
- Multi-user auth, JWT for web clients
- All corporate/team features

### Target: 4 containers
```
core       Python ReAct agent + HTTP API
bot        Telegram bot
admin      React admin panel (simplified)
postgres   Storage (or SQLite for ultra-light mode)
traefik    HTTPS (only if domain provided)
```

---

## Install Wizard (install.sh)

### Steps
1. Pre-checks: docker, docker compose, curl, python3
2. Network: domain or IP:port (auto-detect external IP, find free port)
3. Telegram: paste bot token → bot presses /start → capture owner ID automatically
4. Access policy: DM only or allow groups
5. Models: URL + API key + model name (OpenAI-compatible, any number)
6. Web search: Brave Search API key (optional)
7. Review settings → confirm
8. Generate secrets/, config/, docker-compose.yml
9. docker compose up -d + health check
10. Print URL + admin password

### Security out of the box
- JWT secret: `openssl rand -hex 32` (auto-generated)
- Admin password: `openssl rand -base64 12` (auto-generated, shown once)
- All secrets in files with chmod 600
- No ports exposed except via Traefik (with domain) or single chosen port (IP mode)
- All internal services on bridge network (not reachable from outside)

---

## Admin UI (simplified)

### What to keep
- Chat interface (talk to agent)
- Sessions list
- Scheduled tasks (view/cancel)
- Memory viewer (MEMORY.md)
- Workspace file browser
- Model selector
- Basic settings (bot token, model URL/key, language)
- Logs viewer

### What to remove
- User management / multi-user
- Subscription / billing / usage caps
- Invite links / access codes
- Organization / team settings
- Google OAuth flow (move to optional plugin)
- Bitrix24 integration panel
- LiveKit / voice call UI
- Mobile app deep links
- Dashboard with analytics charts
- Notification feed (overkill for single user)

### Target: ~5 pages
```
/          → Chat (main screen)
/sessions  → Session history
/tasks     → Scheduled tasks
/files     → Workspace file browser
/settings  → Model, bot token, language, memory
```

---

## System Prompt (system.txt)

Best ideas from both DaisyMobile and OpenClaw:

```
<CORE_PRINCIPLE>   Anti-hallucination: tool call SAME response or don't say it
<PERSONA>          Conversational, BAD/GOOD examples, language setting
<SECURITY>         Injection vectors, exfiltration patterns (from DaisyMobile)
<ENVIRONMENT>      {{cwd}}, {{date}}, {{ports}}, sandbox info
<TOOLS>            Dynamic from available tools
<SKILLS>           npx skills ecosystem + builtin skills
<SCHEDULED_TASKS>  Silence filter: only send if genuinely important
```

---

## Web Search (Brave)

- Brave Search API as default web search tool
- `tools/web.py` — `search_web(query)` calls Brave API
- Fallback: DuckDuckGo scrape (no key needed, slower)
- Optional: Tavily, Perplexity as alternatives (user sets in admin)

---

## Roadmap

### v0.1 — Core (now)
- [ ] install.sh wizard
- [ ] Stripped docker-compose.yml (4 containers)
- [ ] Core agent with tools (bash, web, files, memory, scheduler)
- [ ] Telegram bot (single-user)
- [ ] Simplified admin UI (5 pages)
- [ ] Brave Search integration

### v0.2 — Polish
- [ ] Skills system (npx skills ecosystem)
- [ ] MCP support (docker, filesystem)
- [ ] Vision (multimodal models)
- [ ] Voice messages (Whisper ASR, optional)

### v0.3 — Optional plugins
- [ ] Google Workspace (Gmail, Calendar)
- [ ] Web app (simple chat, no mobile app)
- [ ] Self-update via admin UI
