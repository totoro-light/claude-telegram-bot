#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="claude-telegram-bot"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"

# --- Helpers ---
info()  { echo "[info]  $*"; }
warn()  { echo "[warn]  $*"; }
die()   { echo "[error] $*" >&2; exit 1; }

# --- Checks ---
[[ $EUID -ne 0 ]] && die "Run as root or with sudo."
command -v python3 >/dev/null || die "python3 not found."
command -v pip3    >/dev/null || die "pip3 not found."
command -v claude  >/dev/null || die "claude CLI not found — install Claude Code first."

# --- .env setup ---
ENV_FILE="$SCRIPT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating .env from .env.example"
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# Prompt for token if still placeholder
if grep -q "your_bot_token_here" "$ENV_FILE"; then
    read -rp "Enter your Telegram bot token: " token
    [[ -z "$token" ]] && die "Bot token is required."
    sed -i "s|your_bot_token_here|${token}|" "$ENV_FILE"
fi

# --- Python deps ---
info "Installing Python dependencies"
pip3 install -q -r "$SCRIPT_DIR/requirements.txt"

# --- Systemd service ---
info "Installing systemd service"

# Build service file with the actual install path
sed "s|/home/ubuntu/w/totoro-light/claude-telegram-bot|${SCRIPT_DIR}|g" \
    "$SCRIPT_DIR/${SERVICE_NAME}.service" > "$SERVICE_DST"

chmod 644 "$SERVICE_DST"
systemctl daemon-reload
systemctl enable  "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service is running."
    info "Logs: journalctl -u ${SERVICE_NAME} -f"
else
    warn "Service failed to start. Check: journalctl -u ${SERVICE_NAME} -xe"
    exit 1
fi
