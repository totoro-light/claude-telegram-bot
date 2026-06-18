import os
from pathlib import Path

BOT_TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WORK_DIR         = os.environ.get("CLAUDE_WORK_DIR", "/data/w/exx")
SESSIONS_FILE    = Path.home() / ".claude-telegram-sessions.json"
SKIP_PERMISSIONS = os.environ.get("CLAUDE_SKIP_PERMISSIONS", "true").lower() == "true"
ALLOWED_USERS    = set(filter(None, os.environ.get("ALLOWED_USERS", "").split(",")))
