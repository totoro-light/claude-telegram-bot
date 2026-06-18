import json
from config import SESSIONS_FILE


def _load() -> dict:
    if SESSIONS_FILE.exists():
        return json.loads(SESSIONS_FILE.read_text())
    return {}

def _save(data: dict) -> None:
    SESSIONS_FILE.write_text(json.dumps(data, indent=2))

def get(chat_id: int) -> str | None:
    return _load().get(str(chat_id))

def set(chat_id: int, session_id: str) -> None:
    d = _load(); d[str(chat_id)] = session_id; _save(d)

def delete(chat_id: int) -> None:
    d = _load(); d.pop(str(chat_id), None); _save(d)
