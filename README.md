# Claude Code Telegram Bot

A Telegram bot that bridges to [Claude Code](https://claude.ai/code) CLI, letting you interact with Claude from your phone. Includes a skill registry system — installable, reusable tools for Claude backed by this repo.

## Features

- Multi-turn conversations with Claude Code over Telegram
- Per-chat session management
- Skill registry: install GitHub-backed skills with `/skills install <name>`
- `/status` shows repos, Claude context usage, installed skills, and running services
- Runs as a systemd service with auto-restart

## Project structure

```
bot.py          — entry point
config.py       — env vars and constants
session.py      — per-chat session storage
claude.py       — Claude CLI runner
handlers.py     — Telegram command and message handlers
skills/         — skill registry (see below)
skills.json     — project skill manifest
```

---

## Setup

### 1. Prerequisites

- Python 3.11+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### 2. Clone and install dependencies

```bash
git clone https://github.com/totoro-light/claude-telegram-bot
cd claude-telegram-bot
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `GITHUB_TOKEN` | For skills | Classic PAT with `repo` scope — [generate here](https://github.com/settings/tokens) |
| `CLAUDE_WORK_DIR` | No | Directory Claude operates in (default: `/data/w/exx`) |
| `CLAUDE_SKIP_PERMISSIONS` | No | Skip Claude tool permission prompts (default: `true`) |
| `ALLOWED_USERS` | No | Comma-separated Telegram user IDs. Empty = allow all |

### 4. Run

**Directly:**
```bash
python3 bot.py
```

**As a systemd service:**
```bash
# Edit the paths in the service file first
sudo cp claude-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now claude-telegram-bot
```

---

## Bot commands

| Command | Description |
|---|---|
| `/start` / `/help` | Show help |
| `/new` / `/reset` | Clear context and start a fresh conversation |
| `/status` | Show repos, Claude context usage, installed skills, and services |
| `/session` | Show the current Claude session ID |
| `/dir` | Show the working directory Claude operates in |
| `/restart` | Restart the bot service |

Send any message to interact with Claude Code.

---

## Skill system

Skills are hybrid `.md` files — human-readable prose combined with executable Python code blocks. They live in `~/.claude/skills/` globally and are managed by the `/skills` meta-skill.

### Install a skill

First bootstrap the skill manager itself (one-time):

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/totoro-light/claude-telegram-bot/contents/skills/skills.md" \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d['content']).decode())" \
  > ~/.claude/skills/skills.md
```

Then from Claude Code:

```
/skills install github-pr
/skills list
/skills update github-pr
/skills remove github-pr
```

### Install all skills for a project

Declare skills in `skills.json`:

```json
{
  "registry": "totoro-light/claude-telegram-bot",
  "skills": {
    "github-pr": "1.0.0"
  }
}
```

Then run `/skills install` with no arguments — Claude reads `skills.json` and installs everything listed.

### Available skills

| Skill | Description | Requires |
|---|---|---|
| `skills` | Manage skills from the registry | `GITHUB_TOKEN` |
| `github-pr` | Create, list, review, merge, and manage pull requests | `GITHUB_TOKEN` |

### Skill file format

Skills use YAML frontmatter followed by prose and executable Python blocks:

```markdown
---
name: my-skill
description: What this skill does
version: 1.0.0
author: your-username
dependencies: []
env:
  - GITHUB_TOKEN   # classic PAT, scope: repo
---

Describe what this skill does.

## Setup

```python
# @setup
import os, sys
TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("GITHUB_TOKEN not set.")
    sys.exit(1)
```

## Action: example

```python
# @action: example
print("hello from my skill")
```
```

- `# @setup` — runs first, every time
- `# @action: name` — Claude picks the matching block based on the user's request
- `env:` — vars this skill needs; `/status` shows ✓ ready or ⚠ missing

See [`skills/TEMPLATE.md`](skills/TEMPLATE.md) for the full template.

---

## License

MIT
