#!/usr/bin/env bash
# LocalTaskClaw — update to latest version
set -euo pipefail

INSTALL_DIR="${LOCALTASKCLAW_DIR:-$HOME/.localtaskclaw}"
CODE_DIR="$INSTALL_DIR/app"
VENV_DIR="$INSTALL_DIR/venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# Can run headless (called from API) or interactive
QUIET="${1:-}"

log()  { [[ "$QUIET" == "--quiet" ]] || echo -e "$1"; }
fail() { echo -e "${RED}[!] $1${NC}" >&2; exit 1; }

log "${BOLD}LocalTaskClaw — Update${NC}"
log ""

# Verify code directory exists and is a git repo
[[ -d "$CODE_DIR/.git" ]] || fail "Git repo not found at $CODE_DIR"

# 1. Pull latest code
log "[1/3] Pulling latest code..."
cd "$CODE_DIR"
OLD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if ! git pull --rebase --quiet 2>/tmp/ltc-update.log; then
  # If rebase fails (local changes), try merge
  git rebase --abort 2>/dev/null || true
  git pull --quiet 2>>/tmp/ltc-update.log || fail "Git pull failed: $(cat /tmp/ltc-update.log)"
fi

NEW_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [[ "$OLD_HASH" == "$NEW_HASH" ]]; then
  log "${GREEN}Already up to date ($NEW_HASH)${NC}"
else
  log "${GREEN}Updated: $OLD_HASH -> $NEW_HASH${NC}"
fi

# 2. Update dependencies if requirements changed
log "[2/4] Checking dependencies..."
if [[ -f "$CODE_DIR/requirements.txt" && -d "$VENV_DIR" ]]; then
  "$VENV_DIR/bin/pip" install -q -r "$CODE_DIR/requirements.txt" 2>/dev/null || true
fi

# 3. Rebuild frontend if it exists
log "[3/4] Building frontend..."
if [[ -f "$CODE_DIR/frontend/package.json" ]]; then
  if command -v npm &>/dev/null; then
    cd "$CODE_DIR/frontend"
    npm install --silent 2>/dev/null || true
    npm run build 2>/dev/null || log "${YELLOW}Frontend build failed — using existing admin/${NC}"
    cd "$CODE_DIR"
  else
    log "${YELLOW}npm not found — skipping frontend build${NC}"
  fi
fi

# 4. Restart services
log "[4/4] Restarting services..."

if [[ "$(uname -s)" == "Darwin" ]]; then
  LAUNCH_DIR="$HOME/Library/LaunchAgents"
  for svc in core bot; do
    plist="$LAUNCH_DIR/io.localtaskclaw.${svc}.plist"
    if [[ -f "$plist" ]]; then
      launchctl unload "$plist" 2>/dev/null || true
      launchctl load "$plist" 2>/dev/null || true
    fi
  done
elif command -v systemctl &>/dev/null; then
  systemctl --user restart localtaskclaw-core localtaskclaw-bot 2>/dev/null || true
else
  # Fallback: kill and restart via nohup
  pkill -f '\.localtaskclaw/.*main\.py' 2>/dev/null || true
  sleep 1
  SECRETS_DIR="$INSTALL_DIR/secrets"
  cd "$CODE_DIR/core"
  ENV_FILE="$SECRETS_DIR/core.env" \
    nohup "$VENV_DIR/bin/python" -m uvicorn api:app --host 0.0.0.0 --port 11387 \
    > /tmp/localtaskclaw-core.log 2>&1 &
  cd "$CODE_DIR/bot"
  ENV_FILE="$SECRETS_DIR/bot.env" \
    nohup "$VENV_DIR/bin/python" main.py \
    > /tmp/localtaskclaw-bot.log 2>&1 &
fi

log ""
log "${GREEN}${BOLD}Update complete! ($NEW_HASH)${NC}"
