#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/alpaca-paper-bot}"
ENV_FILE="${ENV_FILE:-/etc/alpaca-paper-bot.env}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[install] repo=$REPO_ROOT app=$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3-venv
fi

sudo timedatectl set-timezone Europe/Istanbul

sudo mkdir -p "$APP_DIR"
sudo tar \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='app_profile' \
  -C "$REPO_ROOT" -cf - . | sudo tar -C "$APP_DIR" -xf -
sudo chown -R "$USER:$USER" "$APP_DIR"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$ENV_FILE" ]; then
  sudo cp "$APP_DIR/deploy/vps/alpaca-paper-bot.env.example" "$ENV_FILE"
  sudo chmod 600 "$ENV_FILE"
  echo "[install] created $ENV_FILE; edit it with your Alpaca paper keys before enabling execute mode."
fi

sudo cp "$APP_DIR/deploy/vps/alpaca-paper-bot-main.service" /etc/systemd/system/alpaca-paper-bot-main.service
sudo cp "$APP_DIR/deploy/vps/alpaca-paper-bot-main.timer" /etc/systemd/system/alpaca-paper-bot-main.timer
sudo cp "$APP_DIR/deploy/vps/alpaca-paper-bot-close.service" /etc/systemd/system/alpaca-paper-bot-close.service
sudo cp "$APP_DIR/deploy/vps/alpaca-paper-bot-close.timer" /etc/systemd/system/alpaca-paper-bot-close.timer

sudo systemctl daemon-reload
sudo systemctl enable --now alpaca-paper-bot-main.timer
sudo systemctl enable --now alpaca-paper-bot-close.timer

echo "[install] timers enabled"
systemctl list-timers 'alpaca-paper-bot-*.timer' --all
echo
echo "Next:"
echo "  sudo nano $ENV_FILE"
echo "  sudo systemctl start alpaca-paper-bot-main.service   # optional smoke test"
echo "  journalctl -u alpaca-paper-bot-main.service -f"
