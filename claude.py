import asyncio
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from config import WORK_DIR, SKIP_PERMISSIONS


async def run(prompt: str, session_id: str | None) -> tuple[str, str | None, str | None]:
    """Returns (response_text, new_session_id, error_message)."""
    import json
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


async def keep_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(4)
