#!/usr/bin/env python3
"""
Telegram bot bridge for Claude Code CLI.
Each chat maintains its own session. Supports multi-turn conversations.
"""
import asyncio
import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WORK_DIR = os.environ.get("CLAUDE_WORK_DIR", "/data/w/exx")
SESSIONS_FILE = Path.home() / ".claude-telegram-sessions.json"
SKIP_PERMISSIONS = os.environ.get("CLAUDE_SKIP_PERMISSIONS", "true").lower() == "true"
# Comma-separated Telegram user IDs allowed to use the bot. Empty = allow all.
ALLOWED_USERS = set(filter(None, os.environ.get("ALLOWED_USERS", "").split(",")))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Session storage ---

def _load() -> dict:
    if SESSIONS_FILE.exists():
        return json.loads(SESSIONS_FILE.read_text())
    return {}

def _save(data: dict) -> None:
    SESSIONS_FILE.write_text(json.dumps(data, indent=2))

def get_session(chat_id: int) -> str | None:
    return _load().get(str(chat_id))

def set_session(chat_id: int, session_id: str) -> None:
    d = _load(); d[str(chat_id)] = session_id; _save(d)

def del_session(chat_id: int) -> None:
    d = _load(); d.pop(str(chat_id), None); _save(d)


# --- Auth ---

def allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    return str(update.effective_user.id) in ALLOWED_USERS


# --- Claude runner ---

async def run_claude(prompt: str, session_id: str | None) -> tuple[str, str | None, str | None]:
    """Returns (response_text, new_session_id, error_message)."""
    cmd = ["claude", "-p", "--output-format", "json"]
    if SKIP_PERMISSIONS:
        cmd.append("--dangerously-skip-permissions")
    if session_id:
        cmd.extend(["--resume", session_id])
    cmd.append(prompt)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=WORK_DIR,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        try: proc.kill()
        except Exception: pass
        return "", session_id, "Timed out after 5 minutes."

    if proc.returncode != 0:
        err = stderr.decode().strip() or f"Exit code {proc.returncode}"
        return "", session_id, err[:2000]

    try:
        data = json.loads(stdout.decode())
        if data.get("is_error"):
            return "", session_id, data.get("result", "Unknown error")[:2000]
        return data.get("result", ""), data.get("session_id", session_id), None
    except json.JSONDecodeError:
        return stdout.decode().strip(), session_id, None


# --- Typing keepalive ---

async def keep_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(4)


# --- Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text(
        "*Claude Code Bot*\n\n"
        "Send any message to interact with Claude Code\\.\n\n"
        "Commands:\n"
        "/new — Start a fresh conversation\n"
        "/session — Show current session ID\n"
        "/dir — Show working directory\n"
        "/help — Show this help",
        parse_mode="MarkdownV2",
    )

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    del_session(update.effective_chat.id)
    await update.message.reply_text("Started a new conversation.")

async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    sid = get_session(update.effective_chat.id)
    if sid:
        await update.message.reply_text(f"Session: `{sid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("No active session yet.")

async def cmd_dir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text(f"Working directory: `{WORK_DIR}`", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return

    chat_id = update.effective_chat.id
    text = update.message.text

    stop = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(context, chat_id, stop))

    try:
        session_id = get_session(chat_id)
        response, new_session_id, error = await run_claude(text, session_id)

        if error:
            await update.message.reply_text(f"*Error:* {error}", parse_mode="Markdown")
            return

        if new_session_id and new_session_id != session_id:
            set_session(chat_id, new_session_id)

        if not response:
            await update.message.reply_text("_(empty response)_", parse_mode="Markdown")
            return

        # Telegram max message length is 4096 chars
        for chunk in [response[i:i+4000] for i in range(0, len(response), 4000)]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)  # plain text fallback

    finally:
        stop.set()
        typing_task.cancel()


# --- Main ---

def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Export it before running.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("session", cmd_session))
    app.add_handler(CommandHandler("dir", cmd_dir))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot (work_dir=%s, skip_permissions=%s)", WORK_DIR, SKIP_PERMISSIONS)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
