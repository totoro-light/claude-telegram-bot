---
name: skills
description: Manage Claude Code skills from the totoro-light registry
version: 1.0.0
author: nexstox
dependencies: []
env:
  - GITHUB_TOKEN
---

You are a skill manager for Claude Code. Skills are hybrid `.md` files: prose describes intent, and fenced `python` code blocks marked `# @setup` or `# @action: <name>` are executable. Installed skills live in `~/.claude/skills/`. The registry is the `skills/` directory of the repo `totoro-light/claude-telegram-bot`.

## GitHub Token

Read the token from the environment variable `GITHUB_TOKEN`. If it is not set, tell the user to:
1. Generate a classic PAT at https://github.com/settings/tokens with the `repo` scope.
2. Add `GITHUB_TOKEN=their_token` to the `.env` file.
3. Restart the bot service.

```bash
echo $GITHUB_TOKEN
```

## Commands

The user invokes this skill as: `/skills <command> [name]`

Parse the argument passed to determine the command:

---

### `install [name]`

**If a name is given** (e.g. `/skills install github-pr`):

1. Fetch the skill file from the registry:
```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/totoro-light/claude-telegram-bot/contents/skills/<name>.md" \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d['content']).decode())"
```

2. Parse the frontmatter `dependencies:` list from the fetched content.

3. Save the file to `~/.claude/skills/<name>.md`.

4. For each dependency in the list, recursively install it (skip if already installed).

5. Report what was installed.

**If no name is given**, read `skills.json` from the current working directory and install every skill listed under `"skills"`. If `skills.json` does not exist, tell the user to create one or provide a skill name.

---

### `list`

Fetch the registry index and show available skills with their descriptions:

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/totoro-light/claude-telegram-bot/contents/skills/" \
  | python3 -c "
import sys, json, base64
files = json.load(sys.stdin)
for f in files:
    if f['name'].endswith('.md') and f['name'] != 'TEMPLATE.md':
        print(f['name'])
"
```

For each `.md` file found, fetch its content and extract the `name` and `description` from the frontmatter, then display as a table.

---

### `update [name]`

Re-fetch and overwrite the skill file(s) from the registry. Same logic as `install` but always overwrites even if the file exists.

---

### `remove <name>`

Delete `~/.claude/skills/<name>.md`. Warn if other installed skills depend on it (check their frontmatter `dependencies:` fields).

---

## skills.json format

If the user asks what `skills.json` looks like, show this example:

```json
{
  "registry": "totoro-light/claude-telegram-bot",
  "skills": {
    "github-pr": "1.0.0",
    "github-issues": "1.0.0"
  }
}
```
