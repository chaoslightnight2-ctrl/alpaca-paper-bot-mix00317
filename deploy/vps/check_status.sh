#!/usr/bin/env bash
set -euo pipefail

timedatectl
systemctl list-timers 'alpaca-paper-bot-*.timer' --all
systemctl status alpaca-paper-bot-main.timer --no-pager || true
systemctl status alpaca-paper-bot-close.timer --no-pager || true
journalctl -u alpaca-paper-bot-main.service -n 80 --no-pager || true
journalctl -u alpaca-paper-bot-close.service -n 80 --no-pager || true
