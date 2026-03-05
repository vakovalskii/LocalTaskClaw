#!/usr/bin/env bash
# LocalTaskClaw — запуск core + bot локально
# Использование: ./run.sh [stop|restart|status|logs]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS="$SCRIPT_DIR/secrets/core.env"
VENV="$SCRIPT_DIR/venv"

# ── Цвета ─────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[→]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Проверки ──────────────────────────────────────────────────────────────────
[[ -f "$SECRETS" ]] || error "Нет $SECRETS. Скопируй secrets-template/core.env → secrets/core.env и заполни."

# ── Virtualenv ────────────────────────────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
  info "Создаю virtualenv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/core/requirements.txt"
  [[ -f "$SCRIPT_DIR/bot/requirements.txt" ]] && \
    "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/bot/requirements.txt"
  success "Зависимости установлены"
fi

# ── Команды управления ────────────────────────────────────────────────────────
cmd="${1:-start}"

pid_core() { pgrep -f "localtaskclaw.*core/main" 2>/dev/null | head -1 || true; }
pid_bot()  { pgrep -f "localtaskclaw.*bot/main"  2>/dev/null | head -1 || true; }

case "$cmd" in

  stop)
    info "Останавливаю..."
    pkill -f "localtaskclaw.*core/main" 2>/dev/null && success "core остановлен" || warn "core не запущен"
    pkill -f "localtaskclaw.*bot/main"  2>/dev/null && success "bot остановлен"  || warn "bot не запущен"
    exit 0
    ;;

  status)
    CPID=$(pid_core); BPID=$(pid_bot)
    echo ""
    [[ -n "$CPID" ]] && echo -e "  core  ${GREEN}● running${NC} (pid $CPID)" || echo -e "  core  ${RED}● stopped${NC}"
    [[ -n "$BPID" ]] && echo -e "  bot   ${GREEN}● running${NC} (pid $BPID)" || echo -e "  bot   ${RED}● stopped${NC}"
    echo ""

    # Load port from env
    PORT=$(grep -E '^API_PORT=' "$SECRETS" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo 8000)
    [[ -n "$CPID" ]] && echo -e "  Admin UI → ${BOLD}http://localhost:${PORT}/admin${NC}"
    echo ""
    exit 0
    ;;

  restart)
    "$0" stop
    sleep 1
    exec "$0" start
    ;;

  logs)
    src="${2:-core}"
    tail -f "/tmp/localtaskclaw-${src}.log" 2>/dev/null || echo "Лог /tmp/localtaskclaw-${src}.log не найден"
    exit 0
    ;;

  start) ;;  # fall through
  *) echo "Использование: $0 [start|stop|restart|status|logs]"; exit 1 ;;
esac

# ── START ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}  LocalTaskClaw${NC}"
echo ""

# Stop old instances
pkill -f "localtaskclaw.*core/main" 2>/dev/null || true
pkill -f "localtaskclaw.*bot/main"  2>/dev/null  || true
sleep 0.5

# Load config
set -a; source "$SECRETS"; set +a
PORT="${API_PORT:-8000}"

# Start core
info "Запускаю core на порту $PORT..."
ENV_FILE="$SECRETS" \
  nohup "$VENV/bin/python" "$SCRIPT_DIR/core/main.py" \
  > /tmp/localtaskclaw-core.log 2>&1 &
CORE_PID=$!

# Brief wait then check it started
sleep 2
if ! kill -0 $CORE_PID 2>/dev/null; then
  error "core упал. Логи: tail -f /tmp/localtaskclaw-core.log"
fi

# Wait for core to be ready
for i in $(seq 1 15); do
  if curl -s --max-time 1 "http://localhost:${PORT}/health" &>/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -s --max-time 1 "http://localhost:${PORT}/health" &>/dev/null; then
  warn "Core ещё не ответил на /health, но продолжаем..."
fi
success "core запущен (pid $CORE_PID)"

# Start bot
info "Запускаю bot..."
CORE_URL="http://localhost:${PORT}" \
  nohup "$VENV/bin/python" "$SCRIPT_DIR/bot/main.py" \
  > /tmp/localtaskclaw-bot.log 2>&1 &
BOT_PID=$!
sleep 1
if ! kill -0 $BOT_PID 2>/dev/null; then
  warn "bot упал. Логи: tail -f /tmp/localtaskclaw-bot.log"
else
  success "bot запущен (pid $BOT_PID)"
fi

echo ""
echo -e "${GREEN}${BOLD}  Готово!${NC}"
echo -e "  Admin UI  →  ${BOLD}http://localhost:${PORT}/admin${NC}"
echo -e "  Логи core →  tail -f /tmp/localtaskclaw-core.log"
echo -e "  Логи bot  →  tail -f /tmp/localtaskclaw-bot.log"
echo -e "  Стоп      →  ./run.sh stop"
echo ""
