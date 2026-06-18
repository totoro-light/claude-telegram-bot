#!/usr/bin/env python3
"""Telegram bot bridge for Claude Code CLI."""
import logging
import signal

from telegram.ext import Application, CommandHandler, MessageHandler, filters

import handlers
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], handlers.cmd_start))
    app.add_handler(CommandHandler(["new", "reset"], handlers.cmd_new))
    app.add_handler(CommandHandler("restart", handlers.cmd_restart))
    app.add_handler(CommandHandler("status",  handlers.cmd_status))
    app.add_handler(CommandHandler("session", handlers.cmd_session))
    app.add_handler(CommandHandler("dir",     handlers.cmd_dir))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))

    from config import WORK_DIR, SKIP_PERMISSIONS
    logging.getLogger(__name__).info(
        "Starting bot (work_dir=%s, skip_permissions=%s)", WORK_DIR, SKIP_PERMISSIONS
    )
    app.run_polling(drop_pending_updates=True, stop_signals=(signal.SIGTERM, signal.SIGINT))


if __name__ == "__main__":
    main()
