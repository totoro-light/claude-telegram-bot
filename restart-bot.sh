#!/usr/bin/env bash
# Restart the bot service after a short delay, detached from the current process group.
# Use this instead of calling `systemctl restart` directly from within the bot — otherwise
# systemd kills this process (the bot) before it can finish responding to Telegram.
#
# Usage: bash restart-bot.sh [--now]
#   --now  skip the 3-second delay (useful in scripts that already waited)

set -euo pipefail

DELAY=3
[[ "${1:-}" == "--now" ]] && DELAY=0

(
    sleep "$DELAY"
    systemctl daemon-reload
    systemctl restart claude-telegram-bot
) &>/dev/null &
disown

echo "Restart scheduled in ${DELAY}s (PID $!)."
