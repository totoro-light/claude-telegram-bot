import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

import claude
import session
from config import ALLOWED_USERS, WORK_DIR

RESTART_SCRIPT = Path(__file__).parent / "restart-bot.sh"


def allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    return str(update.effective_user.id) in ALLOWED_USERS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text(
        "*Claude Code Bot*\n\n"
        "Send any message to interact with Claude Code\\.\n\n"
        "Commands:\n"
        "/new or /reset — Clear context, start fresh\n"
        "/restart — Restart this bot service\n"
        "/status — Show repos, branches and services\n"
        "/session — Show current session ID\n"
        "/dir — Show working directory\n"
        "/skills — List installed skills; `/skills list` to browse registry\n"
        "/i\\_feat `<repo> [branch:<name>] <description>` — Plan and implement a feature interactively\n"
        "/help — Show this help",
        parse_mode="MarkdownV2",
    )


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    chat_id = update.effective_chat.id
    old_sid = session.get(chat_id)
    session.delete(chat_id)
    if old_sid:
        msg = f"Context reset.\n\nCleared session: `{old_sid[:8]}...`\nReady for a fresh task."
    else:
        msg = "No active session — already fresh."
    await update.message.reply_text(msg, parse_mode="Markdown")


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
    sid = session.get(update.effective_chat.id)
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

    _append_context_usage(lines)
    _append_skills(lines)
    _append_services(lines)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _append_context_usage(lines: list) -> None:
    try:
        projects_dir = Path.home() / ".claude" / "projects"
        MODEL_LIMIT = 200_000
        latest_usage, latest_mtime = None, 0
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir(): continue
            for session_file in project_dir.glob("*.jsonl"):
                mtime = session_file.stat().st_mtime
                if mtime < latest_mtime: continue
                last = None
                for line in session_file.read_text().splitlines():
                    if not line.strip(): continue
                    try:
                        e = json.loads(line)
                        if e.get("type") == "assistant":
                            u = e.get("message", {}).get("usage")
                            if u: last = u
                    except Exception:
                        pass
                if last:
                    latest_usage = last
                    latest_mtime = mtime

        if not latest_usage: return
        total = (
            latest_usage.get("input_tokens", 0)
            + latest_usage.get("cache_read_input_tokens", 0)
            + latest_usage.get("cache_creation_input_tokens", 0)
            + latest_usage.get("output_tokens", 0)
        )
        used_pct = total / MODEL_LIMIT * 100
        BAR_WIDTH = 20
        filled = used_pct / 100 * BAR_WIDTH
        full_blocks = int(filled)
        half = "▌" if (filled - full_blocks) >= 0.5 else ""
        bar = "█" * full_blocks + half + "░" * (BAR_WIDTH - full_blocks - len(half))
        lines.append(f"\n*Claude Context:*")
        lines.append(f"  `{bar}` {used_pct:.1f}% used")
        lines.append(f"  {total:,} / {MODEL_LIMIT:,} tokens ({100 - used_pct:.1f}% remaining)")
    except Exception:
        pass


def _parse_frontmatter(text: str) -> dict:
    """Extract key/value pairs from YAML frontmatter between --- markers."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    result, current_list_key = {}, None
    for line in match.group(1).splitlines():
        list_item = re.match(r"^\s+-\s+(.+)", line)
        kv = re.match(r"^(\w+):\s*(.*)", line)
        if list_item and current_list_key:
            result[current_list_key].append(list_item.group(1).strip())
        elif kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val in ("[]", ""):
                result[key] = []
                current_list_key = key if val == "" else None
            else:
                result[key] = val
                current_list_key = None
    return result


def _append_skills(lines: list) -> None:
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.exists():
        return
    skill_files = sorted(skills_dir.glob("*.md"))
    if not skill_files:
        return
    lines.append("\n*Skills:*")
    for path in skill_files:
        try:
            meta = _parse_frontmatter(path.read_text())
            name = meta.get("name", path.stem)
            desc = meta.get("description", "")
            required_env = meta.get("env", [])
            missing = [e for e in required_env if not os.environ.get(e)]
            if missing:
                status = f"⚠ missing: {', '.join(f'`{e}`' for e in missing)}"
            else:
                status = "✓ ready" if required_env else "✓"
            lines.append(f"  `{name}` — {desc}  {status}")
        except Exception:
            lines.append(f"  `{path.stem}` — (unreadable)")


def _append_services(lines: list) -> None:
    SYSTEM_KEYWORDS = ["system", "snap", "apt", "dbus", "network", "cron", "ssh",
                       "multipathd", "udev", "getty", "accounts", "polkit", "rsyslog", "unattended"]
    try:
        svc_out = subprocess.check_output(
            ["systemctl", "list-units", "--state=running", "--type=service",
             "--no-pager", "--no-legend"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        project_svcs = [
            l.split()[0] for l in svc_out.splitlines()
            if not any(s in l for s in SYSTEM_KEYWORDS)
        ]
        if project_svcs:
            lines.append("\n*Services:*")
            for s in project_svcs:
                lines.append(f"  `{s}` running")
    except Exception:
        pass


async def _invoke_claude(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_id = update.effective_chat.id

    stop = asyncio.Event()
    typing_task = asyncio.create_task(claude.keep_typing(context, chat_id, stop))

    try:
        session_id = session.get(chat_id)
        response, new_session_id, error = await claude.run(text, session_id)

        if error:
            await update.message.reply_text(f"*Error:* {error}", parse_mode="Markdown")
            return

        if new_session_id and new_session_id != session_id:
            session.set(chat_id, new_session_id)

        if not response:
            await update.message.reply_text("_(empty response)_", parse_mode="Markdown")
            return

        for chunk in [response[i:i+4000] for i in range(0, len(response), 4000)]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)

    finally:
        stop.set()
        typing_task.cancel()


async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    args = " ".join(context.args) if context.args else ""

    if not args:
        lines = ["*Installed Skills:*\n"]
        skills_dir = Path.home() / ".claude" / "skills"
        if not skills_dir.exists() or not list(skills_dir.glob("*.md")):
            lines.append("No skills installed yet.")
            lines.append("\nUse `/skills list` to see available skills in the registry.")
            lines.append("Use `/skills install <name>` to install one.")
        else:
            for path in sorted(skills_dir.glob("*.md")):
                try:
                    meta = _parse_frontmatter(path.read_text())
                    name = meta.get("name", path.stem)
                    desc = meta.get("description", "")
                    version = meta.get("version", "")
                    required_env = meta.get("env", [])
                    missing = [e for e in required_env if not os.environ.get(e)]
                    if missing:
                        status = f"⚠ missing env: {', '.join(missing)}"
                    else:
                        status = f"v{version}" if version else "✓"
                    lines.append(f"`/{name}` — {desc}  _{status}_")
                except Exception:
                    lines.append(f"`/{path.stem}` — (unreadable)")
            lines.append("\n`/skills list` — browse registry  |  `/skills install <name>` — install")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    skill_path = Path.home() / ".claude" / "skills" / "skills.md"
    if skill_path.exists():
        skill_content = skill_path.read_text()
        prompt = f"{skill_content}\n\n---\n\nThe user has invoked this skill with: /skills {args}"
    else:
        prompt = f"Manage Claude Code skills. The user ran: /skills {args}"
    await _invoke_claude(update, context, prompt)


async def cmd_i_feat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text(
            "Usage: `/i_feat <repo> [branch:<name>] <description>`\n\nExample:\n`/i_feat my-app add user authentication`",
            parse_mode="Markdown",
        )
        return
    skill_path = Path.home() / ".claude" / "skills" / "i-feat.md"
    if skill_path.exists():
        skill_content = skill_path.read_text()
        prompt = f"{skill_content}\n\n---\n\nThe user has invoked this skill with: /i-feat {args}"
    else:
        prompt = f"Help the user plan and implement a new feature. Args: {args}"
    await _invoke_claude(update, context, prompt)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await _invoke_claude(update, context, update.message.text)
