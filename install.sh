#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# LocalClaw — Install Wizard
# Usage: curl -fsSL https://raw.githubusercontent.com/vakovalskii/LocalClaw/main/install.sh | bash
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

REPO_URL="https://github.com/vakovalskii/LocalClaw"
SPINNER_PID=""

# --- Helpers -----------------------------------------------------------------

print_header() {
  echo ""
  echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${CYAN}║          🤖  LocalClaw  Installer             ║${NC}"
  echo -e "${BOLD}${CYAN}║       Персональный ИИ-агент за 5 минут        ║${NC}"
  echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${NC}"
  echo ""
}

info()    { echo -e "${BLUE}[→]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}── $* ${NC}"; }
dim()     { echo -e "${DIM}$*${NC}"; }

prompt() {
  local var_name="$1" message="$2" default="${3:-}" input
  if [[ -n "$default" ]]; then
    echo -ne "${BOLD}$message${NC} ${YELLOW}[${default}]${NC}: "
  else
    echo -ne "${BOLD}$message${NC}: "
  fi
  read -r input
  [[ -z "$input" && -n "$default" ]] && input="$default"
  eval "$var_name='$input'"
}

prompt_secret() {
  local var_name="$1" message="$2" input
  echo -ne "${BOLD}$message${NC}: "
  read -rs input; echo ""
  eval "$var_name='$input'"
}

spinner_start() {
  local msg="$1"
  echo -ne "${BLUE}[…]${NC} $msg "
  (while true; do
    for c in '⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏'; do
      echo -ne "\r${BLUE}[$c]${NC} $msg "
      sleep 0.1
    done
  done) &
  SPINNER_PID=$!
  disown "$SPINNER_PID" 2>/dev/null || true
}

spinner_stop() {
  if [[ -n "$SPINNER_PID" ]]; then
    kill "$SPINNER_PID" 2>/dev/null || true
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
    echo -ne "\r\033[K"
  fi
}

write_secret() {
  printf '%s' "$2" > "$1"
  chmod 600 "$1"
}

generate_secret() {
  if command -v openssl &>/dev/null; then
    openssl rand -hex 24
  else
    python3 -c "import secrets; print(secrets.token_hex(24))"
  fi
}

cleanup() {
  spinner_stop; echo ""
  warn "Установка прервана."; exit 130
}
trap cleanup INT TERM


# =============================================================================
# HEADER
# =============================================================================

print_header

# =============================================================================
# ШАГ 1 — ВЫБОР РЕЖИМА ИЗОЛЯЦИИ
# =============================================================================

step "Шаг 1 — Как установить агента?"

echo ""
echo -e "  ${BOLD}1)${NC} 🐳 ${BOLD}Docker${NC} — с изоляцией ${CYAN}(рекомендуем для сервера)${NC}"
dim "       Агент запускается в контейнерах. Доступ только к выделенному тому."
echo ""
echo -e "  ${BOLD}2)${NC} ⚡ ${BOLD}Процессы${NC} — без изоляции, напрямую"
dim "       Агент работает как Python-процесс. Видит всю файловую систему."
echo ""
echo -e "  ${BOLD}3)${NC} 📁 ${BOLD}Ограничить папкой агента${NC} — процессы + sandbox"
dim "       Как вариант 2, но агент заперт в ~/.localclaw/workspace."
echo ""
prompt INSTALL_MODE "Выбор" "1"

case "$INSTALL_MODE" in
  2) MODE_NAME="native"     ;;
  3) MODE_NAME="restricted" ;;
  *) MODE_NAME="docker"     ;;
esac

success "Режим: ${BOLD}${MODE_NAME}${NC}"

# =============================================================================
# ШАГ 2 — ПРОВЕРКА ЗАВИСИМОСТЕЙ
# =============================================================================

step "Шаг 2 — Проверка зависимостей"

# python3 нужен всегда (для поллинга Telegram)
if ! command -v python3 &>/dev/null; then
  error "python3 не найден. Установи: brew install python3 / apt install python3"
  exit 1
fi
success "Python $(python3 --version | awk '{print $2}')"

if ! command -v curl &>/dev/null; then
  error "curl не найден"
  exit 1
fi
success "curl найден"

if [[ "$MODE_NAME" == "docker" ]]; then
  if ! command -v docker &>/dev/null; then
    error "Docker не найден → https://docs.docker.com/engine/install/"
    exit 1
  fi
  if ! docker info &>/dev/null; then
    error "Docker daemon не запущен. Запусти: sudo systemctl start docker"
    exit 1
  fi
  success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
  else
    error "Docker Compose не найден → https://docs.docker.com/compose/install/"
    exit 1
  fi
  success "Compose: $COMPOSE_CMD"

else
  # Native / restricted — нужен git и pip
  if ! command -v git &>/dev/null; then
    error "git не найден. Установи: brew install git / apt install git"
    exit 1
  fi
  success "git $(git --version | awk '{print $3}')"

  if ! python3 -m pip --version &>/dev/null 2>&1; then
    error "pip не найден. Запусти: python3 -m ensurepip --upgrade"
    exit 1
  fi
  success "pip найден"
fi

# =============================================================================
# ШАГ 3 — TELEGRAM БОТ
# =============================================================================

step "Шаг 3 — Telegram бот"

TG_TOKEN="" BOT_USERNAME="" OWNER_ID="" OWNER_NAME=""

while true; do
  prompt_secret TG_TOKEN "Токен бота (от @BotFather)"
  if ! echo "$TG_TOKEN" | grep -qE '^[0-9]+:[A-Za-z0-9_-]{30,}$'; then
    error "Неверный формат. Должно быть: 1234567890:ABCdef..."
    continue
  fi
  spinner_start "Проверяю токен..."
  BOT_INFO=$(curl -s --max-time 10 "https://api.telegram.org/bot${TG_TOKEN}/getMe" 2>/dev/null || echo '{"ok":false}')
  spinner_stop
  BOT_OK=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('yes' if d.get('ok') else 'no')" <<< "$BOT_INFO")
  if [[ "$BOT_OK" == "yes" ]]; then
    BOT_USERNAME=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d['result']['username'])" <<< "$BOT_INFO")
    success "Бот: @${BOLD}${BOT_USERNAME}${NC}"
    break
  else
    BOT_ERR=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('description','unknown'))" <<< "$BOT_INFO")
    error "Ошибка: $BOT_ERR"
  fi
done

echo ""
info "Открой бота ${BOLD}@${BOT_USERNAME}${NC} в Telegram и нажми ${BOLD}/start${NC}"
info "Жду сообщение... (120 сек, или Ctrl+C и введи ID вручную)"
echo ""

RESULT=$(python3 - "$TG_TOKEN" <<'PYEOF'
import sys, json, urllib.request, time

token = sys.argv[1]
offset = 0

try:
    url = f"https://api.telegram.org/bot{token}/getUpdates?limit=1&offset=-1"
    r = urllib.request.urlopen(url, timeout=5)
    data = json.loads(r.read())
    updates = data.get("result", [])
    if updates:
        offset = updates[-1]["update_id"] + 1
except:
    pass

deadline = time.time() + 120
dots = 0
while time.time() < deadline:
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2&offset={offset}&allowed_updates=%5B%22message%22%5D"
        r = urllib.request.urlopen(url, timeout=5)
        data = json.loads(r.read())
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message", {})
            if msg.get("text", "").startswith("/start"):
                uid  = msg.get("from", {}).get("id", "")
                name = msg.get("from", {}).get("first_name", "User")
                print(f"FOUND:{uid}:{name}")
                sys.exit(0)
    except:
        pass
    dots = (dots + 1) % 4
    print(f"\r  Ожидание{'.' * dots}   ", end="", flush=True)
    time.sleep(2)

print("\rTIMEOUT" + " " * 30)
sys.exit(1)
PYEOF
) || true

if echo "$RESULT" | grep -q "^FOUND:"; then
  OWNER_ID=$(echo "$RESULT"   | grep "^FOUND:" | head -1 | cut -d: -f2)
  OWNER_NAME=$(echo "$RESULT" | grep "^FOUND:" | head -1 | cut -d: -f3-)
  success "Владелец: ${BOLD}${OWNER_NAME}${NC} (ID: ${BOLD}${OWNER_ID}${NC})"
else
  warn "Не получил /start за 120 сек."
  prompt OWNER_ID "Введи Telegram ID вручную" ""
  OWNER_NAME="Owner"
fi

# =============================================================================
# ШАГ 4 — LLM МОДЕЛЬ
# =============================================================================

step "Шаг 4 — Языковая модель"

echo "  ${BOLD}1)${NC} Ollama — локальная модель на этом сервере ${CYAN}(рекомендуем)${NC}"
echo "  ${BOLD}2)${NC} Внешний API — OpenAI / свой сервер / облако"
echo ""
prompt MODEL_SOURCE "Выбор" "1"

LLM_BASE_URL="" LLM_API_KEY="" MODEL_NAME=""
USE_OLLAMA=""

if [[ "$MODEL_SOURCE" == "1" ]]; then
  USE_OLLAMA="yes"

  # Hardware detection
  TOTAL_RAM_GB=0 GPU_VRAM_GB=0
  TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
  TOTAL_RAM_GB=$(( TOTAL_RAM_KB / 1024 / 1024 ))
  if command -v nvidia-smi &>/dev/null; then
    GPU_VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ' || echo "0")
    GPU_VRAM_GB=$(( GPU_VRAM_MB / 1024 ))
  fi

  AVAILABLE_GB=$TOTAL_RAM_GB
  [[ "$GPU_VRAM_GB" -gt 4 ]] && AVAILABLE_GB=$GPU_VRAM_GB
  info "RAM: ${BOLD}${TOTAL_RAM_GB}GB${NC}  GPU VRAM: ${BOLD}${GPU_VRAM_GB}GB${NC}"
  echo ""

  declare -A MODEL_OPTIONS
  OPT_NUM=1
  add_model_option() {
    local min_gb="$1" name="$2" tag="$3" size="$4" note="$5"
    if [[ "$AVAILABLE_GB" -ge "$min_gb" ]]; then
      echo "  ${BOLD}${OPT_NUM})${NC} ${name}:${tag}  ${YELLOW}(${size})${NC}  — ${note}"
      MODEL_OPTIONS["$OPT_NUM"]="${name}:${tag}"
      OPT_NUM=$((OPT_NUM + 1))
    fi
  }

  add_model_option 3  "qwen2.5"     "3b"   "2.0GB" "минимум RAM"
  add_model_option 6  "qwen2.5"     "7b"   "4.7GB" "★ отличный tool use"
  add_model_option 10 "llama3.1"    "8b"   "4.9GB" "Meta, хорош для кода"
  add_model_option 12 "qwen2.5"     "14b"  "9.0GB" "★★ сильный reasoning"
  add_model_option 22 "qwen2.5"     "32b"  "19GB"  "★★★ лучший до 32GB"
  add_model_option 22 "deepseek-r1" "14b"  "9.0GB" "reasoning + цепочка мыслей"
  add_model_option 50 "qwen2.5"     "72b"  "47GB"  "топ open-source"
  CUSTOM_OPT=$OPT_NUM
  echo "  ${BOLD}${OPT_NUM})${NC} Ввести своё название"
  echo ""

  prompt OLLAMA_CHOICE "Выбор" "1"

  if [[ "$OLLAMA_CHOICE" == "$CUSTOM_OPT" ]]; then
    prompt MODEL_NAME "Название модели (например: mistral:7b)" ""
  elif [[ -n "${MODEL_OPTIONS[$OLLAMA_CHOICE]:-}" ]]; then
    MODEL_NAME="${MODEL_OPTIONS[$OLLAMA_CHOICE]}"
  else
    MODEL_NAME="${MODEL_OPTIONS[1]:-qwen2.5:7b}"
  fi

  success "Выбрана модель: ${BOLD}${MODEL_NAME}${NC}"

  # Install Ollama
  if command -v ollama &>/dev/null; then
    success "Ollama уже установлен"
  else
    info "Устанавливаю Ollama..."
    spinner_start "Установка Ollama..."
    if curl -fsSL https://ollama.com/install.sh | sh > /tmp/ollama_install.log 2>&1; then
      spinner_stop; success "Ollama установлен"
    else
      spinner_stop; error "Ошибка установки Ollama:"; tail -10 /tmp/ollama_install.log; exit 1
    fi
  fi

  # Start Ollama
  if ! curl -s --max-time 2 http://localhost:11434/ &>/dev/null; then
    info "Запускаю Ollama..."
    if command -v systemctl &>/dev/null && systemctl is-enabled ollama &>/dev/null 2>&1; then
      systemctl start ollama
    else
      nohup ollama serve > /tmp/ollama.log 2>&1 &
      sleep 3
    fi
  fi

  # Pull model
  echo ""
  info "Скачиваю ${BOLD}${MODEL_NAME}${NC}..."
  if ! ollama pull "$MODEL_NAME"; then
    error "Ошибка скачивания. Попробуй вручную: ollama pull ${MODEL_NAME}"
    exit 1
  fi
  success "Модель скачана"

  if [[ "$MODE_NAME" == "docker" ]]; then
    LLM_BASE_URL="http://host.docker.internal:11434/v1"
  else
    LLM_BASE_URL="http://localhost:11434/v1"
  fi
  LLM_API_KEY="ollama"

else
  # External API
  info "Примеры URL: https://api.openai.com/v1  /  http://your-server:44334/v1"
  echo ""
  prompt    LLM_BASE_URL "Base URL" ""
  prompt_secret LLM_API_KEY  "API ключ"
  prompt    MODEL_NAME   "Название модели" "gpt-4o"
  success   "Модель: ${BOLD}${MODEL_NAME}${NC}"
fi

# =============================================================================
# ШАГ 5 — ВЕБ-ПОИСК
# =============================================================================

step "Шаг 5 — Веб-поиск (Brave)"
dim "  Получить ключ: https://api.search.brave.com/"
echo ""
echo -ne "${BOLD}Brave API key${NC} ${YELLOW}[Enter = пропустить]${NC}: "
read -rs BRAVE_KEY; echo ""
if [[ -n "$BRAVE_KEY" ]]; then
  success "Brave Search подключён"
else
  warn "Веб-поиск отключён (добавишь позже в Settings)"
fi

# =============================================================================
# ШАГ 6 — ПОДТВЕРЖДЕНИЕ
# =============================================================================

step "Шаг 6 — Проверка"

echo ""
echo -e "${BOLD}┌──────────────────────────────────────────────┐${NC}"
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "Режим"         "$MODE_NAME"
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "Telegram бот"  "@$BOT_USERNAME"
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "Владелец"      "$OWNER_NAME ($OWNER_ID)"
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "Модель"        "$MODEL_NAME"
SHORT_URL="$LLM_BASE_URL"
[[ ${#SHORT_URL} -gt 25 ]] && SHORT_URL="${SHORT_URL:0:22}..."
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "LLM URL"       "$SHORT_URL"
printf "${BOLD}│${NC} %-18s %-25s ${BOLD}│${NC}\n" "Brave Search"  "${BRAVE_KEY:+подключён}${BRAVE_KEY:-отключён}"
echo -e "${BOLD}└──────────────────────────────────────────────┘${NC}"
echo ""
echo -ne "${BOLD}Запустить установку? [Y/n]${NC}: "
read -r CONFIRM; CONFIRM="${CONFIRM:-Y}"
[[ "$CONFIRM" =~ ^[Yy] ]] || { info "Отменено."; exit 0; }

# =============================================================================
# УСТАНОВКА — DOCKER
# =============================================================================

if [[ "$MODE_NAME" == "docker" ]]; then
  INSTALL_DIR="$HOME/localclaw"
  mkdir -p "$INSTALL_DIR/secrets" "$INSTALL_DIR/workspace" "$INSTALL_DIR/data"

  API_SECRET=$(generate_secret)

  write_secret "$INSTALL_DIR/secrets/bot_token.txt"    "$TG_TOKEN"
  write_secret "$INSTALL_DIR/secrets/owner_id.txt"     "$OWNER_ID"
  write_secret "$INSTALL_DIR/secrets/api_secret.txt"   "$API_SECRET"
  write_secret "$INSTALL_DIR/secrets/llm_api_key.txt"  "$LLM_API_KEY"
  [[ -n "$BRAVE_KEY" ]] && write_secret "$INSTALL_DIR/secrets/brave_api_key.txt" "$BRAVE_KEY"

  cat > "$INSTALL_DIR/docker-compose.yml" << COMPOSE
services:
  core:
    image: ghcr.io/vakovalskii/localclaw-core:latest
    container_name: localclaw-core
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MODEL=${MODEL_NAME}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - LLM_API_KEY_FILE=/run/secrets/llm_api_key
      - BOT_TOKEN_FILE=/run/secrets/bot_token
      - OWNER_ID=${OWNER_ID}
      - API_SECRET_FILE=/run/secrets/api_secret
      - WORKSPACE=/workspace
      - DB_PATH=/data/localclaw.db
      - BRAVE_API_KEY_FILE=/run/secrets/brave_api_key
      - MAX_ITERATIONS=20
      - COMMAND_TIMEOUT=60
    secrets:
      - bot_token
      - api_secret
      - llm_api_key
      - brave_api_key
    volumes:
      - ./workspace:/workspace
      - ./data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  bot:
    image: ghcr.io/vakovalskii/localclaw-bot:latest
    container_name: localclaw-bot
    restart: unless-stopped
    depends_on:
      core:
        condition: service_healthy
    environment:
      - CORE_URL=http://core:8000
      - BOT_TOKEN_FILE=/run/secrets/bot_token
      - API_SECRET_FILE=/run/secrets/api_secret
      - OWNER_ID=${OWNER_ID}
    secrets:
      - bot_token
      - api_secret

secrets:
  bot_token:
    file: ./secrets/bot_token.txt
  api_secret:
    file: ./secrets/api_secret.txt
  llm_api_key:
    file: ./secrets/llm_api_key.txt
  brave_api_key:
    file: ./secrets/${BRAVE_KEY:+brave_api_key.txt}${BRAVE_KEY:-api_secret.txt}
COMPOSE

  success "Конфиг: ${BOLD}$INSTALL_DIR${NC}"

  info "Запускаю контейнеры..."
  cd "$INSTALL_DIR"
  spinner_start "docker compose up -d..."
  if ! $COMPOSE_CMD up -d > /tmp/localclaw_up.log 2>&1; then
    spinner_stop
    error "Ошибка запуска:"; tail -20 /tmp/localclaw_up.log; exit 1
  fi
  spinner_stop; success "Контейнеры запущены"

  # Health check
  spinner_start "Жду готовности..."
  HEALTHY=false
  for i in $(seq 1 30); do
    if curl -s --max-time 2 http://localhost:8000/health &>/dev/null; then
      HEALTHY=true; break
    fi
    sleep 2
  done
  spinner_stop
  [[ "$HEALTHY" == "true" ]] && success "Сервис готов!" || warn "Сервис ещё загружается..."

  ADMIN_URL="http://localhost:8000/admin"
  MANAGE_INFO="Логи:    ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml logs -f${NC}
Стоп:    ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml down${NC}
Обновить: ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml pull && $COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml up -d${NC}"

fi

# =============================================================================
# УСТАНОВКА — NATIVE / RESTRICTED
# =============================================================================

if [[ "$MODE_NAME" == "native" || "$MODE_NAME" == "restricted" ]]; then

  if [[ "$MODE_NAME" == "restricted" ]]; then
    WORKSPACE_DIR="$HOME/.localclaw/workspace"
    INSTALL_DIR="$HOME/.localclaw"
  else
    WORKSPACE_DIR="$HOME/.localclaw/workspace"
    INSTALL_DIR="$HOME/localclaw"
  fi
  DB_PATH="$HOME/.localclaw/localclaw.db"
  VENV_DIR="$INSTALL_DIR/venv"
  CODE_DIR="$INSTALL_DIR/app"

  mkdir -p "$INSTALL_DIR" "$WORKSPACE_DIR" "$HOME/.localclaw"

  # Clone repo
  if [[ -d "$CODE_DIR/.git" ]]; then
    info "Обновляю код..."
    git -C "$CODE_DIR" pull --rebase --quiet
  else
    info "Клонирую репозиторий..."
    spinner_start "git clone..."
    if ! git clone --quiet "$REPO_URL" "$CODE_DIR" > /tmp/localclaw_clone.log 2>&1; then
      spinner_stop; error "Ошибка клонирования:"; tail -5 /tmp/localclaw_clone.log; exit 1
    fi
    spinner_stop; success "Код скачан"
  fi

  # Virtual environment
  if [[ ! -d "$VENV_DIR" ]]; then
    info "Создаю виртуальное окружение..."
    python3 -m venv "$VENV_DIR"
  fi

  info "Устанавливаю зависимости..."
  spinner_start "pip install..."
  if ! "$VENV_DIR/bin/pip" install -q -r "$CODE_DIR/core/requirements.txt" > /tmp/localclaw_pip.log 2>&1; then
    spinner_stop; error "Ошибка pip:"; tail -10 /tmp/localclaw_pip.log; exit 1
  fi
  if [[ -f "$CODE_DIR/bot/requirements.txt" ]]; then
    "$VENV_DIR/bin/pip" install -q -r "$CODE_DIR/bot/requirements.txt" >> /tmp/localclaw_pip.log 2>&1 || true
  fi
  spinner_stop; success "Зависимости установлены"

  # Generate API secret
  API_SECRET=$(generate_secret)

  # Write secrets/core.env
  SECRETS_DIR="$CODE_DIR/secrets"
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"

  cat > "$SECRETS_DIR/core.env" << ENV
# LocalClaw Core — generated by installer
# DO NOT COMMIT

MODEL=${MODEL_NAME}
LLM_BASE_URL=${LLM_BASE_URL}
LLM_API_KEY=${LLM_API_KEY}

BOT_TOKEN=${TG_TOKEN}
OWNER_ID=${OWNER_ID}

API_SECRET=${API_SECRET}

WORKSPACE=${WORKSPACE_DIR}
DB_PATH=${DB_PATH}

BRAVE_API_KEY=${BRAVE_KEY:-}

MAX_ITERATIONS=20
COMMAND_TIMEOUT=60
MAX_TOKENS=4096
API_PORT=8000
ENV
  chmod 600 "$SECRETS_DIR/core.env"
  success "Конфиг: ${BOLD}$SECRETS_DIR/core.env${NC}"

  # Write bot config
  cat > "$SECRETS_DIR/bot.env" << ENV
CORE_URL=http://localhost:8000
BOT_TOKEN=${TG_TOKEN}
API_SECRET=${API_SECRET}
OWNER_ID=${OWNER_ID}
ENV
  chmod 600 "$SECRETS_DIR/bot.env"

  # --- macOS: LaunchAgent ---
  if [[ "$(uname -s)" == "Darwin" ]]; then
    LAUNCH_DIR="$HOME/Library/LaunchAgents"
    mkdir -p "$LAUNCH_DIR"

    cat > "$LAUNCH_DIR/io.localclaw.core.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>              <string>io.localclaw.core</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>-m</string><string>uvicorn</string>
    <string>api:app</string>
    <string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8000</string>
  </array>
  <key>WorkingDirectory</key>   <string>${CODE_DIR}/core</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ENV_FILE</key>         <string>${SECRETS_DIR}/core.env</string>
  </dict>
  <key>StandardOutPath</key>    <string>/tmp/localclaw-core.log</string>
  <key>StandardErrorPath</key>  <string>/tmp/localclaw-core.log</string>
  <key>RunAtLoad</key>          <true/>
  <key>KeepAlive</key>          <true/>
</dict>
</plist>
PLIST

    cat > "$LAUNCH_DIR/io.localclaw.bot.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>              <string>io.localclaw.bot</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>${CODE_DIR}/bot/main.py</string>
  </array>
  <key>WorkingDirectory</key>   <string>${CODE_DIR}/bot</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ENV_FILE</key>         <string>${SECRETS_DIR}/bot.env</string>
  </dict>
  <key>StandardOutPath</key>    <string>/tmp/localclaw-bot.log</string>
  <key>StandardErrorPath</key>  <string>/tmp/localclaw-bot.log</string>
  <key>RunAtLoad</key>          <true/>
  <key>KeepAlive</key>          <true/>
</dict>
</plist>
PLIST

    # Load services
    launchctl unload "$LAUNCH_DIR/io.localclaw.core.plist" 2>/dev/null || true
    launchctl unload "$LAUNCH_DIR/io.localclaw.bot.plist"  2>/dev/null || true
    launchctl load   "$LAUNCH_DIR/io.localclaw.core.plist"
    launchctl load   "$LAUNCH_DIR/io.localclaw.bot.plist"
    success "LaunchAgents зарегистрированы (автозапуск при логине)"

  # --- Linux: systemd user units ---
  elif command -v systemctl &>/dev/null; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"

    cat > "$SYSTEMD_DIR/localclaw-core.service" << SVC
[Unit]
Description=LocalClaw Core
After=network.target

[Service]
Type=simple
WorkingDirectory=${CODE_DIR}/core
ExecStart=${VENV_DIR}/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000
Environment=ENV_FILE=${SECRETS_DIR}/core.env
Restart=always
RestartSec=5
StandardOutput=append:/tmp/localclaw-core.log
StandardError=append:/tmp/localclaw-core.log

[Install]
WantedBy=default.target
SVC

    cat > "$SYSTEMD_DIR/localclaw-bot.service" << SVC
[Unit]
Description=LocalClaw Bot
After=localclaw-core.service
Requires=localclaw-core.service

[Service]
Type=simple
WorkingDirectory=${CODE_DIR}/bot
ExecStart=${VENV_DIR}/bin/python main.py
Environment=ENV_FILE=${SECRETS_DIR}/bot.env
Restart=always
RestartSec=5
StandardOutput=append:/tmp/localclaw-bot.log
StandardError=append:/tmp/localclaw-bot.log

[Install]
WantedBy=default.target
SVC

    systemctl --user daemon-reload
    systemctl --user enable --now localclaw-core.service
    systemctl --user enable --now localclaw-bot.service
    success "systemd user units запущены"

  else
    # Fallback: bare nohup
    warn "systemd/launchd не найдены — запускаю через nohup"
    pkill -f "uvicorn api:app" 2>/dev/null || true
    pkill -f "localclaw-bot" 2>/dev/null  || true
    sleep 1
    cd "$CODE_DIR/core"
    ENV_FILE="$SECRETS_DIR/core.env" \
      nohup "$VENV_DIR/bin/python" -m uvicorn api:app --host 0.0.0.0 --port 8000 \
      > /tmp/localclaw-core.log 2>&1 &
    cd "$CODE_DIR/bot"
    ENV_FILE="$SECRETS_DIR/bot.env" \
      nohup "$VENV_DIR/bin/python" main.py \
      > /tmp/localclaw-bot.log 2>&1 &
    success "Процессы запущены (nohup)"
  fi

  # Health check
  spinner_start "Жду готовности сервиса..."
  HEALTHY=false
  for i in $(seq 1 20); do
    if curl -s --max-time 2 http://localhost:8000/health &>/dev/null; then
      HEALTHY=true; break
    fi
    sleep 2
  done
  spinner_stop
  [[ "$HEALTHY" == "true" ]] && success "Core готов!" || warn "Core ещё загружается (см. /tmp/localclaw-core.log)"

  ADMIN_URL="http://localhost:8000/admin"

  if [[ "$(uname -s)" == "Darwin" ]]; then
    MANAGE_INFO="Логи core: ${BOLD}tail -f /tmp/localclaw-core.log${NC}
Логи bot:  ${BOLD}tail -f /tmp/localclaw-bot.log${NC}
Стоп:      ${BOLD}launchctl unload ~/Library/LaunchAgents/io.localclaw.*.plist${NC}
Старт:     ${BOLD}launchctl load ~/Library/LaunchAgents/io.localclaw.*.plist${NC}"
  else
    MANAGE_INFO="Логи core: ${BOLD}tail -f /tmp/localclaw-core.log${NC}
Логи bot:  ${BOLD}tail -f /tmp/localclaw-bot.log${NC}
Стоп:      ${BOLD}systemctl --user stop localclaw-core localclaw-bot${NC}
Старт:     ${BOLD}systemctl --user start localclaw-core localclaw-bot${NC}"
  fi

fi

# =============================================================================
# ФИНАЛ
# =============================================================================

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║          ✅  Установка завершена!                ║${NC}"
echo -e "${BOLD}${GREEN}╠══════════════════════════════════════════════════╣${NC}"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Режим:"         "$MODE_NAME"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Admin UI:"      "$ADMIN_URL"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "API Secret:"    "$API_SECRET"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Telegram бот:"  "@$BOT_USERNAME"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Модель:"        "$MODEL_NAME"
if [[ "$MODE_NAME" == "restricted" ]]; then
  printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Workspace:"   "~/.localclaw/workspace"
fi
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "$MANAGE_INFO"
echo ""
info "Открой в браузере: ${BOLD}${ADMIN_URL}${NC}"
info "Используй API Secret как пароль для входа в UI"
echo ""
