#!/usr/bin/env bash
# LocalTaskClaw — полное удаление с системы
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="$HOME/.localtaskclaw"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo ""
echo -e "${BOLD}${RED}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${RED}║         LocalTaskClaw — Удаление                      ║${NC}"
echo -e "${BOLD}${RED}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Show what will be removed
echo -e "${BOLD}Будет удалено:${NC}"
echo ""

[[ -d "$INSTALL_DIR" ]] && echo -e "  ${YELLOW}~/.localtaskclaw/${NC}  (приложение, venv, БД, секреты, workspace)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  for f in "$LAUNCH_DIR"/io.localtaskclaw.*.plist; do
    [[ -f "$f" ]] && echo -e "  ${YELLOW}$(basename "$f")${NC}  (LaunchAgent)" && break
  done
else
  for f in "$SYSTEMD_DIR"/localtaskclaw-*.service; do
    [[ -f "$f" ]] && echo -e "  ${YELLOW}$(basename "$f")${NC}  (systemd unit)" && break
  done
fi

echo ""
echo -e "${RED}${BOLD}Это действие необратимо! Все данные, секреты и workspace будут удалены.${NC}"
echo ""
echo -ne "${BOLD}Продолжить удаление? [y/N]${NC}: "
read -r CONFIRM
[[ "$CONFIRM" =~ ^[Yy] ]] || { echo "Отменено."; exit 0; }

echo ""

# 1. Stop services
echo -e "[1/4] ${BOLD}Останавливаю сервисы...${NC}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  for f in "$LAUNCH_DIR"/io.localtaskclaw.*.plist; do
    if [[ -f "$f" ]]; then
      launchctl unload "$f" 2>/dev/null || true
      echo "  unloaded $(basename "$f")"
    fi
  done
else
  systemctl --user stop localtaskclaw-core localtaskclaw-bot 2>/dev/null || true
  systemctl --user disable localtaskclaw-core localtaskclaw-bot 2>/dev/null || true
  echo "  stopped systemd services"
fi

# Kill any remaining processes
pkill -f 'localtaskclaw.*main\.py' 2>/dev/null || true
pkill -f 'LocalTaskClaw/bot/main\.py' 2>/dev/null || true
pkill -f 'LocalTaskClaw/core' 2>/dev/null || true
pkill -f '\.localtaskclaw/.*main\.py' 2>/dev/null || true

# 2. Remove LaunchAgent / systemd files
echo -e "[2/4] ${BOLD}Удаляю автозапуск...${NC}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  rm -f "$LAUNCH_DIR"/io.localtaskclaw.*.plist 2>/dev/null
  echo "  removed LaunchAgent plists"
else
  rm -f "$SYSTEMD_DIR"/localtaskclaw-*.service 2>/dev/null
  systemctl --user daemon-reload 2>/dev/null || true
  echo "  removed systemd units"
fi

# 3. Remove install directory
echo -e "[3/4] ${BOLD}Удаляю файлы...${NC}"

if [[ -d "$INSTALL_DIR" ]]; then
  rm -rf "$INSTALL_DIR"
  echo "  removed $INSTALL_DIR"
else
  echo "  $INSTALL_DIR не найден (уже удалён?)"
fi

# 4. Clean up logs
echo -e "[4/4] ${BOLD}Очищаю логи...${NC}"
rm -f /tmp/localtaskclaw-core.log /tmp/localtaskclaw-bot.log 2>/dev/null
echo "  removed /tmp/localtaskclaw-*.log"

# Also remove old LocalClaw dirs if they exist
for old_dir in "$HOME/LocalTaskClaw" "$HOME/LocalClaw"; do
  if [[ -d "$old_dir" ]]; then
    echo ""
    echo -ne "  Найдена старая папка ${YELLOW}$old_dir${NC}. Удалить? [y/N]: "
    read -r DEL_OLD
    if [[ "$DEL_OLD" =~ ^[Yy] ]]; then
      rm -rf "$old_dir"
      echo "  removed $old_dir"
    fi
  fi
done

echo ""
echo -e "${GREEN}${BOLD}LocalTaskClaw полностью удалён.${NC}"
echo ""
