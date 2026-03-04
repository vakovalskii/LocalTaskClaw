#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# LocalClaw — Install Wizard
# Deploys a personal AI agent on any Linux server in 3 steps.
# Usage: curl -fsSL https://raw.githubusercontent.com/vakovalskii/LocalClaw/main/install.sh | bash
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="$HOME/localclaw"
SPINNER_PID=""

# --- Helpers -----------------------------------------------------------------

print_header() {
  echo ""
  echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${CYAN}║        🤖 LocalClaw Installer           ║${NC}"
  echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo ""
}

info()    { echo -e "${BLUE}[→]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}── $* ${NC}"; }

prompt() {
  local var_name="$1"
  local message="$2"
  local default="${3:-}"
  local input
  if [[ -n "$default" ]]; then
    echo -ne "${BOLD}$message${NC} ${YELLOW}[${default}]${NC}: "
  else
    echo -ne "${BOLD}$message${NC}: "
  fi
  read -r input
  if [[ -z "$input" && -n "$default" ]]; then
    input="$default"
  fi
  eval "$var_name='$input'"
}

prompt_secret() {
  local var_name="$1"
  local message="$2"
  local input
  echo -ne "${BOLD}$message${NC}: "
  read -rs input
  echo ""
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
  local file="$1"
  local value="$2"
  printf '%s' "$value" > "$file"
  chmod 600 "$file"
}

generate_password() {
  if command -v openssl &>/dev/null; then
    openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16
  else
    python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16)))"
  fi
}

generate_secret() {
  if command -v openssl &>/dev/null; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

cleanup() {
  spinner_stop
  echo ""
  warn "Установка прервана."
  exit 130
}
trap cleanup INT TERM

# --- Step 1: Pre-checks ------------------------------------------------------

print_header

step "Шаг 1/7 — Проверка зависимостей"

# Docker
if ! command -v docker &>/dev/null; then
  error "Docker не найден."
  echo "  Установи: https://docs.docker.com/engine/install/"
  exit 1
fi
if ! docker info &>/dev/null; then
  error "Docker daemon не запущен. Запусти: sudo systemctl start docker"
  exit 1
fi
success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# Docker Compose
if docker compose version &>/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
else
  error "Docker Compose не найден."
  echo "  Установи: https://docs.docker.com/compose/install/"
  exit 1
fi
success "Compose: $COMPOSE_CMD"

# curl
if ! command -v curl &>/dev/null; then
  error "curl не найден. Установи: apt-get install curl / yum install curl"
  exit 1
fi
success "curl найден"

# python3
if ! command -v python3 &>/dev/null; then
  error "python3 не найден. Установи: apt-get install python3"
  exit 1
fi
success "python3 $(python3 --version | awk '{print $2}')"

# --- Step 2: Network ---------------------------------------------------------

step "Шаг 2/7 — Режим установки"

echo "  ${BOLD}1)${NC} 🐳 Docker  — изолированно, для сервера ${CYAN}(рекомендуем)${NC}"
echo "  ${BOLD}2)${NC} ⚡ Native  — без Docker, для MacBook / ноута"
echo ""
prompt INSTALL_MODE "Выбор" "1"

if [[ "$INSTALL_MODE" == "2" ]]; then
  # Native mode pre-checks
  NATIVE_MODE="yes"
  if ! command -v python3 &>/dev/null; then
    error "python3 не найден. Установи: brew install python3 / apt install python3"
    exit 1
  fi
  if ! python3 -m pip --version &>/dev/null 2>&1; then
    error "pip не найден. Установи: python3 -m ensurepip"
    exit 1
  fi
  success "Native mode: Python $(python3 --version | awk '{print $2}')"
  INSTALL_DIR="$HOME/.localclaw"
else
  NATIVE_MODE=""
  success "Docker mode"
fi

step "Шаг 3/7 — Сеть"

USE_DOMAIN=""
DOMAIN=""
ACCESS_SCHEME="http"
ACCESS_PORT=""
SERVER_IP=""

# Detect external IP
spinner_start "Определяю внешний IP..."
SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || curl -s --max-time 5 api.ipify.org 2>/dev/null || echo "")
spinner_stop
if [[ -z "$SERVER_IP" ]]; then
  warn "Не удалось определить внешний IP автоматически."
  prompt SERVER_IP "Введи внешний IP сервера" ""
else
  success "Внешний IP: ${BOLD}$SERVER_IP${NC}"
fi

echo ""
echo -ne "${BOLD}Есть домен для HTTPS? [y/N]${NC}: "
read -r domain_answer
domain_answer="${domain_answer:-N}"

if [[ "$domain_answer" =~ ^[Yy] ]]; then
  prompt DOMAIN "Домен (например: agent.example.com)" ""
  # Check DNS
  spinner_start "Проверяю DNS для $DOMAIN..."
  DNS_IP=""
  if command -v dig &>/dev/null; then
    DNS_IP=$(dig +short "$DOMAIN" A 2>/dev/null | head -1 || echo "")
  else
    DNS_IP=$(python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('https://dns.google/resolve?name=$DOMAIN&type=A', timeout=5)
    d = json.loads(r.read())
    ans = d.get('Answer', [])
    if ans: print(ans[-1]['data'])
except: pass
" 2>/dev/null || echo "")
  fi
  spinner_stop
  if [[ -z "$DNS_IP" ]]; then
    warn "DNS не резолвится. Убедись что A-запись настроена."
  elif [[ "$DNS_IP" != "$SERVER_IP" ]]; then
    warn "DNS указывает на ${BOLD}$DNS_IP${NC}, а сервер ${BOLD}$SERVER_IP${NC}."
    warn "Let's Encrypt может не выдать сертификат. Продолжить?"
    echo -ne "${BOLD}Продолжить? [y/N]${NC}: "
    read -r cont_answer
    [[ "$cont_answer" =~ ^[Yy] ]] || { info "Установка отменена."; exit 0; }
  else
    success "DNS OK: $DOMAIN → $DNS_IP"
  fi
  ACCESS_SCHEME="https"
  ACCESS_PORT="443"
  USE_DOMAIN="yes"
else
  # Find free port
  spinner_start "Ищу свободный порт..."
  FREE_PORT=""
  for p in 80 8080 3000 8443 8888 9000; do
    IS_BUSY=$(ss -ltn 2>/dev/null | grep -c ":$p " || netstat -ltn 2>/dev/null | grep -c ":$p " || python3 -c "
import socket
s = socket.socket()
try:
    s.bind(('', $p)); s.close(); print('0')
except: print('1')
" 2>/dev/null || echo "1")
    if [[ "$IS_BUSY" == "0" ]]; then
      FREE_PORT="$p"
      break
    fi
  done
  spinner_stop
  if [[ -z "$FREE_PORT" ]]; then
    prompt FREE_PORT "Не нашёл свободный порт. Введи вручную" "8080"
  fi
  prompt ACCESS_PORT "Порт" "$FREE_PORT"
  ACCESS_SCHEME="http"
  warn "HTTPS недоступен без домена. Трафик не зашифрован."
fi

ACCESS_URL="${ACCESS_SCHEME}://${DOMAIN:-$SERVER_IP}${ACCESS_PORT:+:$ACCESS_PORT}"
success "URL: ${BOLD}$ACCESS_URL${NC}"

# --- Step 3: Telegram --------------------------------------------------------

step "Шаг 4/7 — Telegram бот"

TG_TOKEN=""
BOT_USERNAME=""
OWNER_ID=""
OWNER_NAME=""

while true; do
  prompt_secret TG_TOKEN "Вставь токен бота (от @BotFather)"
  # Validate format
  if ! echo "$TG_TOKEN" | grep -qE '^[0-9]+:[A-Za-z0-9_-]{30,}$'; then
    error "Неверный формат токена. Должно быть: 1234567890:ABCdef..."
    continue
  fi
  # Test token
  spinner_start "Проверяю токен..."
  BOT_INFO=$(curl -s --max-time 10 "https://api.telegram.org/bot${TG_TOKEN}/getMe" 2>/dev/null || echo '{"ok":false}')
  spinner_stop
  BOT_OK=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('yes' if d.get('ok') else 'no')" <<< "$BOT_INFO")
  if [[ "$BOT_OK" == "yes" ]]; then
    BOT_USERNAME=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d['result']['username'])" <<< "$BOT_INFO")
    success "Бот найден: @${BOLD}$BOT_USERNAME${NC}"
    break
  else
    BOT_ERR=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('description','unknown error'))" <<< "$BOT_INFO")
    error "Ошибка: $BOT_ERR"
  fi
done

echo ""
info "Теперь открой бота ${BOLD}@${BOT_USERNAME}${NC} в Telegram и нажми ${BOLD}/start${NC}"
info "Жду сообщение... (Ctrl+C для отмены, или введи ID вручную)"
echo ""

# Poll for /start
RESULT=$(python3 - "$TG_TOKEN" <<'PYEOF'
import sys, json, urllib.request, time, datetime

token = sys.argv[1]
offset = 0
deadline = time.time() + 120

# Get current offset to skip old messages
try:
    url = f"https://api.telegram.org/bot{token}/getUpdates?limit=1&offset=-1"
    r = urllib.request.urlopen(url, timeout=5)
    data = json.loads(r.read())
    updates = data.get("result", [])
    if updates:
        offset = updates[-1]["update_id"] + 1
except:
    pass

dots = 0
while time.time() < deadline:
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2&offset={offset}&allowed_updates=%5B%22message%22%5D"
        r = urllib.request.urlopen(url, timeout=5)
        data = json.loads(r.read())
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message", {})
            text = msg.get("text", "")
            from_user = msg.get("from", {})
            if text.startswith("/start"):
                uid = from_user.get("id", "")
                name = from_user.get("first_name", "User")
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
  OWNER_ID=$(echo "$RESULT" | grep "^FOUND:" | head -1 | cut -d: -f2)
  OWNER_NAME=$(echo "$RESULT" | grep "^FOUND:" | head -1 | cut -d: -f3-)
  success "Владелец: ${BOLD}${OWNER_NAME}${NC} (ID: ${BOLD}${OWNER_ID}${NC})"
else
  warn "Не получил /start за 120 секунд."
  prompt OWNER_ID "Введи свой Telegram ID вручную" ""
  OWNER_NAME="Owner"
fi

# --- Step 4: Access policy ---------------------------------------------------

step "Шаг 5/7 — Политика доступа"

echo "  ${BOLD}1)${NC} Только личные сообщения (DM)"
echo "  ${BOLD}2)${NC} DM + разрешённые группы"
echo ""
prompt ACCESS_POLICY "Выбор" "1"

case "$ACCESS_POLICY" in
  2) GROUP_POLICY="allowlist"; info "Группы: разрешённые (добавишь IDs в настройках)" ;;
  *) GROUP_POLICY="disabled"; info "Режим: только DM" ;;
esac

# --- Step 5: Models ----------------------------------------------------------

step "Шаг 6/7 — Модели"

MODEL_URLS=()
MODEL_KEYS=()
MODEL_NAMES=()
USE_OLLAMA=""
OLLAMA_MODEL=""

echo "  ${BOLD}1)${NC} Ollama — локальная модель на этом сервере ${CYAN}(рекомендуем)${NC}"
echo "  ${BOLD}2)${NC} Внешний API — OpenAI, свой сервер, облако"
echo ""
prompt MODEL_SOURCE_CHOICE "Выбор" "1"

if [[ "$MODEL_SOURCE_CHOICE" == "1" ]]; then
  # --- Ollama path ---
  USE_OLLAMA="yes"

  # Detect RAM and GPU
  TOTAL_RAM_GB=0
  GPU_VRAM_GB=0

  TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
  TOTAL_RAM_GB=$(( TOTAL_RAM_KB / 1024 / 1024 ))

  if command -v nvidia-smi &>/dev/null; then
    GPU_VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ' || echo "0")
    GPU_VRAM_GB=$(( GPU_VRAM_MB / 1024 ))
  fi

  info "RAM: ${BOLD}${TOTAL_RAM_GB}GB${NC}  GPU VRAM: ${BOLD}${GPU_VRAM_GB}GB${NC}"
  echo ""

  # Pick available memory (prefer VRAM if GPU present)
  AVAILABLE_GB=$TOTAL_RAM_GB
  [[ "$GPU_VRAM_GB" -gt 4 ]] && AVAILABLE_GB=$GPU_VRAM_GB

  # Model recommendations for agentic cycles (tool use, JSON)
  echo -e "  ${BOLD}Рекомендуемые модели для агентного цикла:${NC}"
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

  add_model_option 3  "qwen2.5"    "3b"   "2.0GB"  "минимум RAM, базовый tool use"
  add_model_option 6  "qwen2.5"    "7b"   "4.7GB"  "★ лучший выбор до 8GB, отличный tool use"
  add_model_option 10 "llama3.1"   "8b"   "4.9GB"  "Meta, хорош для кода"
  add_model_option 12 "qwen2.5"    "14b"  "9.0GB"  "★★ топ под 16GB, сильный reasoning"
  add_model_option 22 "qwen2.5"    "32b"  "19GB"   "★★★ лучший до 32GB"
  add_model_option 22 "deepseek-r1" "14b" "9.0GB"  "reasoning модель (цепочка мыслей)"
  add_model_option 50 "qwen2.5"    "72b"  "47GB"   "топ open-source, нужно 48GB+"
  add_model_option 50 "llama3.3"   "70b"  "43GB"   "Meta flagship"

  LAST_OPT=$((OPT_NUM - 1))
  echo "  ${BOLD}${OPT_NUM})${NC} Ввести своё название модели"
  echo ""

  prompt OLLAMA_CHOICE "Выбор" "1"

  if [[ "$OLLAMA_CHOICE" == "$OPT_NUM" ]]; then
    prompt OLLAMA_MODEL "Название модели (например: mistral:7b)" ""
  elif [[ -n "${MODEL_OPTIONS[$OLLAMA_CHOICE]:-}" ]]; then
    OLLAMA_MODEL="${MODEL_OPTIONS[$OLLAMA_CHOICE]}"
  else
    OLLAMA_MODEL="${MODEL_OPTIONS[1]:-qwen2.5:7b}"
  fi

  success "Выбрана модель: ${BOLD}${OLLAMA_MODEL}${NC}"

  # Install Ollama if not present
  echo ""
  if command -v ollama &>/dev/null; then
    success "Ollama уже установлен $(ollama --version 2>/dev/null || echo '')"
  else
    info "Устанавливаю Ollama..."
    spinner_start "Установка Ollama..."
    if curl -fsSL https://ollama.com/install.sh | sh &>/tmp/ollama_install.log 2>&1; then
      spinner_stop
      success "Ollama установлен"
    else
      spinner_stop
      error "Ошибка установки Ollama:"
      tail -10 /tmp/ollama_install.log
      exit 1
    fi
  fi

  # Start Ollama service if not running
  if ! curl -s --max-time 2 http://localhost:11434/ &>/dev/null; then
    info "Запускаю Ollama service..."
    if command -v systemctl &>/dev/null && systemctl is-enabled ollama &>/dev/null 2>&1; then
      systemctl start ollama
    else
      nohup ollama serve > /tmp/ollama.log 2>&1 &
      sleep 3
    fi
  fi

  # Pull model
  echo ""
  MODEL_SIZE_GB=$(echo "$OLLAMA_MODEL" | python3 -c "
import sys
m = sys.stdin.read().strip()
sizes = {'3b':2,'7b':5,'8b':5,'14b':9,'32b':19,'70b':43,'72b':47}
for k,v in sizes.items():
    if k in m: print(v); exit()
print(5)
")
  info "Скачиваю ${BOLD}${OLLAMA_MODEL}${NC} (~${MODEL_SIZE_GB}GB)..."
  info "Это может занять несколько минут..."
  echo ""
  if ollama pull "$OLLAMA_MODEL"; then
    success "Модель ${BOLD}${OLLAMA_MODEL}${NC} скачана"
  else
    error "Ошибка скачивания модели. Попробуй вручную: ollama pull ${OLLAMA_MODEL}"
    exit 1
  fi

  # Set model config for docker (use host.docker.internal to reach Ollama from container)
  MODEL_URLS=("http://host.docker.internal:11434/v1")
  MODEL_KEYS=("ollama")
  MODEL_NAMES=("$OLLAMA_MODEL")

else
  # --- External API path ---
  info "Добавь хотя бы одну OpenAI-совместимую модель."
  info "Примеры URL: https://api.openai.com/v1  /  http://109.230.162.92:44334/v1"
  echo ""

  while true; do
    IDX=$((${#MODEL_URLS[@]} + 1))
    echo -e "${BOLD}Модель #${IDX}${NC}"
    prompt MODEL_URL "  URL (base URL)" ""
    prompt_secret MODEL_KEY "  API ключ"
    prompt MODEL_NAME "  Название модели" "gpt-4o"

    MODEL_URLS+=("$MODEL_URL")
    MODEL_KEYS+=("$MODEL_KEY")
    MODEL_NAMES+=("$MODEL_NAME")
    success "Модель '${MODEL_NAME}' добавлена"

    echo ""
    echo -ne "${BOLD}Добавить ещё модель? [y/N]${NC}: "
    read -r more_models
    [[ "$more_models" =~ ^[Yy] ]] || break
    echo ""
  done
fi

# --- Step 6: Brave Search ----------------------------------------------------

step "Шаг 6/7 — Веб-поиск (Brave)"

echo "  Получить ключ: ${CYAN}https://api.search.brave.com/${NC}"
echo ""
echo -ne "${BOLD}Brave API key${NC} ${YELLOW}[Enter = пропустить]${NC}: "
read -rs BRAVE_KEY
echo ""
if [[ -n "$BRAVE_KEY" ]]; then
  success "Brave Search подключён"
else
  warn "Веб-поиск отключён (добавишь позже в настройках)"
fi

# --- Step 7: Review ----------------------------------------------------------

step "Шаг 7/7 — Проверка настроек"

echo ""
echo -e "${BOLD}┌──────────────────────────────────────────────┐${NC}"
printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "URL" "$ACCESS_URL"
printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "Telegram бот" "@$BOT_USERNAME"
printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "Владелец" "$OWNER_NAME ($OWNER_ID)"
printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "Группы" "$GROUP_POLICY"
for i in "${!MODEL_NAMES[@]}"; do
  SHORT_URL="${MODEL_URLS[$i]}"
  [[ ${#SHORT_URL} -gt 24 ]] && SHORT_URL="${SHORT_URL:0:21}..."
  printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "Модель $((i+1))" "${MODEL_NAMES[$i]} @ $SHORT_URL"
done
printf "${BOLD}│${NC} %-20s %-24s ${BOLD}│${NC}\n" "Brave Search" "${BRAVE_KEY:+подключён}${BRAVE_KEY:-отключён}"
echo -e "${BOLD}└──────────────────────────────────────────────┘${NC}"
echo ""

echo -ne "${BOLD}Запустить установку? [Y/n]${NC}: "
read -r confirm_answer
confirm_answer="${confirm_answer:-Y}"
[[ "$confirm_answer" =~ ^[Yy] ]] || { info "Отменено."; exit 0; }

# --- Generate files ----------------------------------------------------------

info "Создаю рабочую директорию: ${BOLD}$INSTALL_DIR${NC}"
mkdir -p "$INSTALL_DIR"/{secrets,config,traefik}

# Generate credentials
ADMIN_PASSWORD=$(generate_password)
JWT_SECRET=$(generate_secret)

# Secrets
write_secret "$INSTALL_DIR/secrets/telegram_token.txt"  "$TG_TOKEN"
write_secret "$INSTALL_DIR/secrets/owner_id.txt"        "$OWNER_ID"
write_secret "$INSTALL_DIR/secrets/admin_password.txt"  "$ADMIN_PASSWORD"
write_secret "$INSTALL_DIR/secrets/jwt_secret.txt"      "$JWT_SECRET"
write_secret "$INSTALL_DIR/secrets/model_url.txt"       "${MODEL_URLS[0]}"
write_secret "$INSTALL_DIR/secrets/model_api_key.txt"   "${MODEL_KEYS[0]}"
write_secret "$INSTALL_DIR/secrets/model_name.txt"      "${MODEL_NAMES[0]}"
[[ -n "$BRAVE_KEY" ]] && write_secret "$INSTALL_DIR/secrets/brave_api_key.txt" "$BRAVE_KEY"

# models.json
python3 - "$INSTALL_DIR/config/models.json" "${MODEL_NAMES[*]}" "${MODEL_URLS[*]}" "${MODEL_KEYS[*]}" << 'PYEOF'
import sys, json

out_file = sys.argv[1]
names = sys.argv[2].split()
urls  = sys.argv[3].split()
keys  = sys.argv[4].split()

models = []
for i, (name, url, key) in enumerate(zip(names, urls, keys)):
    models.append({
        "name": name,
        "url": url,
        "api_key": key,
        "default": i == 0
    })

with open(out_file, "w") as f:
    json.dump(models, f, indent=2)
PYEOF

# bot_config.json
python3 - "$INSTALL_DIR/config/bot_config.json" "$OWNER_ID" "$GROUP_POLICY" << 'PYEOF'
import sys, json
out_file, owner_id, group_policy = sys.argv[1], sys.argv[2], sys.argv[3]
with open(out_file, "w") as f:
    json.dump({"owner_id": int(owner_id), "group_policy": group_policy, "access_mode": "owner"}, f, indent=2)
PYEOF

# docker-compose.yml
if [[ "$USE_DOMAIN" == "yes" ]]; then
  BRAVE_SECRET=""
  BRAVE_ENV=""
  [[ -n "$BRAVE_KEY" ]] && BRAVE_SECRET="  brave_api_key:\n    file: ./secrets/brave_api_key.txt" && BRAVE_ENV="      - BRAVE_API_KEY_FILE=/run/secrets/brave_api_key"

  cat > "$INSTALL_DIR/docker-compose.yml" << COMPOSE
services:
  traefik:
    image: traefik:v3
    container_name: traefik
    restart: unless-stopped
    command:
      - "--providers.file.filename=/traefik/config.yml"
      - "--providers.file.watch=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@${DOMAIN}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./traefik:/traefik
      - letsencrypt:/letsencrypt
    networks:
      - agent-net

  core:
    image: ghcr.io/vakovalskii/localclaw-core:latest
    container_name: localclaw-core
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - TZ=Europe/Moscow
      - API_PORT=4000
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=localclaw
      - POSTGRES_USER=localclaw
      - PUBLIC_URL=https://${DOMAIN}
    secrets:
      - postgres_password
      - jwt_secret
      - model_url
      - model_api_key
      - model_name
      - owner_id
      $(echo -e "$BRAVE_ENV")
    volumes:
      - ./workspace:/workspace
      - ./config:/config:ro
    networks:
      - agent-net
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.core.rule=Host(\`${DOMAIN}\`) && PathPrefix(\`/api\`)"
      - "traefik.http.routers.core.entrypoints=websecure"
      - "traefik.http.routers.core.tls.certresolver=letsencrypt"
      - "traefik.http.services.core.loadbalancer.server.port=4000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  bot:
    image: ghcr.io/vakovalskii/localclaw-bot:latest
    container_name: localclaw-bot
    restart: unless-stopped
    depends_on:
      core:
        condition: service_healthy
    environment:
      - CORE_URL=http://core:4000
      - TZ=Europe/Moscow
    secrets:
      - telegram_token
      - owner_id
    networks:
      - agent-net

  admin:
    image: ghcr.io/vakovalskii/localclaw-admin:latest
    container_name: localclaw-admin
    restart: unless-stopped
    depends_on:
      core:
        condition: service_healthy
    environment:
      - TZ=Europe/Moscow
      - ADMIN_USER=admin
    secrets:
      - admin_password
    networks:
      - agent-net
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.admin.rule=Host(\`${DOMAIN}\`)"
      - "traefik.http.routers.admin.entrypoints=websecure"
      - "traefik.http.routers.admin.tls.certresolver=letsencrypt"
      - "traefik.http.services.admin.loadbalancer.server.port=3000"

  postgres:
    image: postgres:16-alpine
    container_name: localclaw-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=localclaw
      - POSTGRES_USER=localclaw
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - agent-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U localclaw"]
      interval: 10s
      timeout: 5s
      retries: 5

secrets:
  telegram_token:
    file: ./secrets/telegram_token.txt
  owner_id:
    file: ./secrets/owner_id.txt
  admin_password:
    file: ./secrets/admin_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  postgres_password:
    file: ./secrets/postgres_password.txt
  model_url:
    file: ./secrets/model_url.txt
  model_api_key:
    file: ./secrets/model_api_key.txt
  model_name:
    file: ./secrets/model_name.txt
$(echo -e "$BRAVE_SECRET")

volumes:
  postgres_data:
  letsencrypt:

networks:
  agent-net:
    driver: bridge
    internal: false
COMPOSE

  # Traefik config
  cat > "$INSTALL_DIR/traefik/config.yml" << TRAEFIK
tls:
  options:
    default:
      minVersion: VersionTLS12
      cipherSuites:
        - TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384
        - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
        - TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305
TRAEFIK

else
  # IP mode — no Traefik
  BRAVE_SECRET=""
  BRAVE_ENV=""
  [[ -n "$BRAVE_KEY" ]] && BRAVE_SECRET="  brave_api_key:\n    file: ./secrets/brave_api_key.txt" && BRAVE_ENV="      - BRAVE_API_KEY_FILE=/run/secrets/brave_api_key"

  cat > "$INSTALL_DIR/docker-compose.yml" << COMPOSE
services:
  core:
    image: ghcr.io/vakovalskii/localclaw-core:latest
    container_name: localclaw-core
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - TZ=Europe/Moscow
      - API_PORT=4000
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=localclaw
      - POSTGRES_USER=localclaw
      - PUBLIC_URL=http://${SERVER_IP}:${ACCESS_PORT}
    secrets:
      - postgres_password
      - jwt_secret
      - model_url
      - model_api_key
      - model_name
      - owner_id
      $(echo -e "$BRAVE_ENV")
    volumes:
      - ./workspace:/workspace
      - ./config:/config:ro
    networks:
      - agent-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  bot:
    image: ghcr.io/vakovalskii/localclaw-bot:latest
    container_name: localclaw-bot
    restart: unless-stopped
    depends_on:
      core:
        condition: service_healthy
    environment:
      - CORE_URL=http://core:4000
      - TZ=Europe/Moscow
    secrets:
      - telegram_token
      - owner_id
    networks:
      - agent-net

  admin:
    image: ghcr.io/vakovalskii/localclaw-admin:latest
    container_name: localclaw-admin
    restart: unless-stopped
    depends_on:
      core:
        condition: service_healthy
    ports:
      - "${ACCESS_PORT}:3000"
    environment:
      - TZ=Europe/Moscow
      - ADMIN_USER=admin
    secrets:
      - admin_password
    networks:
      - agent-net

  postgres:
    image: postgres:16-alpine
    container_name: localclaw-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=localclaw
      - POSTGRES_USER=localclaw
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - agent-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U localclaw"]
      interval: 10s
      timeout: 5s
      retries: 5

secrets:
  telegram_token:
    file: ./secrets/telegram_token.txt
  owner_id:
    file: ./secrets/owner_id.txt
  admin_password:
    file: ./secrets/admin_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  postgres_password:
    file: ./secrets/postgres_password.txt
  model_url:
    file: ./secrets/model_url.txt
  model_api_key:
    file: ./secrets/model_api_key.txt
  model_name:
    file: ./secrets/model_name.txt
$(echo -e "$BRAVE_SECRET")

volumes:
  postgres_data:

networks:
  agent-net:
    driver: bridge
    internal: false
COMPOSE
fi

# Generate postgres password
write_secret "$INSTALL_DIR/secrets/postgres_password.txt" "$(generate_secret | head -c 32)"

success "Конфиг сгенерирован: ${BOLD}$INSTALL_DIR${NC}"

# --- Deploy ------------------------------------------------------------------

echo ""
info "Запускаю контейнеры..."
cd "$INSTALL_DIR"

spinner_start "docker compose up -d..."
if ! $COMPOSE_CMD up -d 2>/tmp/localclaw_up.log; then
  spinner_stop
  error "Ошибка запуска:"
  tail -20 /tmp/localclaw_up.log
  echo ""
  error "Логи контейнеров:"
  $COMPOSE_CMD logs --tail=20 2>/dev/null || true
  exit 1
fi
spinner_stop
success "Контейнеры запущены"

# Health check
spinner_start "Жду готовности сервиса..."
HEALTH_URL="http://127.0.0.1:${ACCESS_PORT:-3000}/health"
HEALTHY=false
for i in $(seq 1 30); do
  if curl -s --max-time 2 "$HEALTH_URL" &>/dev/null; then
    HEALTHY=true
    break
  fi
  sleep 2
done
spinner_stop

if [[ "$HEALTHY" == "true" ]]; then
  success "Сервис готов!"
else
  warn "Сервис ещё не ответил — может быть всё ещё загружается."
fi

# --- Final output ------------------------------------------------------------

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║          ✅  Установка завершена!                ║${NC}"
echo -e "${BOLD}${GREEN}╠══════════════════════════════════════════════════╣${NC}"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "URL:" "$ACCESS_URL"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Логин:" "admin"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Пароль:" "$ADMIN_PASSWORD"
echo -e "${BOLD}${GREEN}║${NC}                                                  ${BOLD}${GREEN}║${NC}"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Telegram бот:" "@$BOT_USERNAME"
printf "${BOLD}${GREEN}║${NC}  %-16s ${BOLD}%-30s${NC} ${BOLD}${GREEN}║${NC}\n" "Модель:" "${MODEL_NAMES[0]}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
if [[ ${#MODEL_NAMES[@]} -gt 1 ]]; then
  info "Все модели: ${MODEL_NAMES[*]}"
fi
echo ""
info "Логи:    ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml logs -f${NC}"
info "Стоп:    ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml down${NC}"
info "Обновить: ${BOLD}$COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml pull && $COMPOSE_CMD -f $INSTALL_DIR/docker-compose.yml up -d${NC}"
echo ""
