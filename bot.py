#!/usr/bin/env python3
"""
Telegram bot bridge for Claude Code CLI.
Each chat maintains its own session. Supports multi-turn conversations.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
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

RESTART_SCRIPT = Path(__file__).parent / "restart-bot.sh"

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text(
        "*Claude Code Bot*\n\n"
        "Send any message to interact with Claude Code\\.\n\n"
        "Commands:\n"
        "/new — Start a fresh conversation\n"
        "/restart — Restart this bot service\n"
        "/status — Show repos, branches and services\n"
        "/session — Show current session ID\n"
        "/dir — Show working directory\n"
        "/help — Show this help",
        parse_mode="MarkdownV2",
    )

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    del_session(update.effective_chat.id)
    await update.message.reply_text("Started a new conversation.")

async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("Restarting bot service in 3 seconds...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(RESTART_SCRIPT),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception as e:
        await update.message.reply_text(f"Failed to schedule restart: {e}")

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

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    lines = [f"*Status* — `{WORK_DIR}`\n"]

    # Repos
    work = Path(WORK_DIR)
    repos = sorted([d for d in work.iterdir() if d.is_dir() and (d / ".git").exists()])
    if repos:
        lines.append("*Repos:*")
        for repo in repos:
            try:
                branch = subprocess.check_output(
                    ["git", "branch", "--show-current"], cwd=repo, stderr=subprocess.DEVNULL
                ).decode().strip() or "HEAD detached"
                dirty = subprocess.check_output(
                    ["git", "status", "--short"], cwd=repo, stderr=subprocess.DEVNULL
                ).decode().strip()
                flag = " \\*" if dirty else ""
                lines.append(f"  `{repo.name}` → {branch}{flag}")
            except Exception:
                lines.append(f"  `{repo.name}` → (error)")
    else:
        lines.append("No git repos found.")

    # Claude Code context usage
    try:
        projects_dir = Path.home() / ".claude" / "projects"
        MODEL_LIMIT = 200_000
        latest_usage = None
        latest_mtime = 0
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for session_file in project_dir.glob("*.jsonl"):
                mtime = session_file.stat().st_mtime
                if mtime < latest_mtime:
                    continue
                # find last assistant usage in this file
                last = None
                for line in session_file.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        e = json.loads(line)
                        if e.get("type") == "assistant":
                            u = e.get("message", {}).get("usage")
                            if u:
                                last = u
                    except Exception:
                        pass
                if last:
                    latest_usage = last
                    latest_mtime = mtime
        if latest_usage:
            total = (
                latest_usage.get("input_tokens", 0)
                + latest_usage.get("cache_read_input_tokens", 0)
                + latest_usage.get("cache_creation_input_tokens", 0)
                + latest_usage.get("output_tokens", 0)
            )
            used_pct = total / MODEL_LIMIT * 100
            remaining_pct = 100 - used_pct
            BAR_WIDTH = 20
            filled = used_pct / 100 * BAR_WIDTH
            full_blocks = int(filled)
            half = "▌" if (filled - full_blocks) >= 0.5 else ""
            empty = BAR_WIDTH - full_blocks - len(half)
            bar = "█" * full_blocks + half + "░" * empty
            lines.append(f"\n*Claude Context:*")
            lines.append(f"  `{bar}` {used_pct:.1f}% used")
            lines.append(f"  {total:,} / {MODEL_LIMIT:,} tokens ({remaining_pct:.1f}% remaining)")
    except Exception:
        pass

    # Services
    try:
        svc_out = subprocess.check_output(
            ["systemctl", "list-units", "--state=running", "--type=service",
             "--no-pager", "--no-legend"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        project_svcs = [
            l.split()[0] for l in svc_out.splitlines()
            if not any(s in l for s in ["system", "snap", "apt", "dbus", "network",
                                         "cron", "ssh", "multipathd", "udev", "getty",
                                         "accounts", "polkit", "rsyslog", "unattended"])
        ]
        if project_svcs:
            lines.append("\n*Services:*")
            for s in project_svcs:
                lines.append(f"  `{s}` running")
    except Exception:
        pass

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("session", cmd_session))
    app.add_handler(CommandHandler("dir", cmd_dir))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot (work_dir=%s, skip_permissions=%s)", WORK_DIR, SKIP_PERMISSIONS)
    app.run_polling(drop_pending_updates=True, stop_signals=(signal.SIGTERM, signal.SIGINT))


if __name__ == "__main__":
    main()
