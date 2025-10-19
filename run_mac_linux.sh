#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 --version >/dev/null
pip3 install -r requirements.txt
if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then read -p "Введите TELEGRAM_BOT_TOKEN: " TELEGRAM_BOT_TOKEN; export TELEGRAM_BOT_TOKEN; fi
python3 main.py || true
read -p "Нажмите Enter, чтобы закрыть окно..." _
