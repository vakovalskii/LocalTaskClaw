# SimpleClaw

Personal AI agent. Deploys in 3 steps on any Linux server.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/vakovalskii/SimpleClaw/main/install.sh | bash
```

## What you get

- Telegram bot connected to your AI models
- Admin UI (chat, sessions, tasks, files, settings)
- Any OpenAI-compatible model (local or cloud)
- Web search via Brave
- HTTPS auto via Let's Encrypt (if you have a domain)
- Works without a domain (IP:port mode)

## Requirements

- Linux server (Ubuntu/Debian/CentOS)
- Docker + Docker Compose
- Telegram Bot Token (from @BotFather)
- OpenAI-compatible model endpoint

## Architecture

4 containers:

| Container | Role |
|-----------|------|
| `core` | Python ReAct agent + API |
| `bot` | Telegram bot |
| `admin` | React admin panel |
| `postgres` | Storage |
| `traefik` | HTTPS (optional, with domain) |

## Status

Work in progress. See [PLAN.md](PLAN.md) for roadmap.
