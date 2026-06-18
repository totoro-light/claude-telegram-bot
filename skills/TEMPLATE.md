---
name: skill-name
description: One-line description of what this skill does
version: 1.0.0
author: your-github-username
dependencies: []
env: []
# env example — list vars this skill requires:
# env:
#   - GITHUB_TOKEN   # classic PAT, scope: repo (https://github.com/settings/tokens)
---

Describe what this skill does and when to use it. This prose is for humans and Claude to read.

## Setup

Explain any prerequisites. Claude runs setup blocks once before the main action.

```python
import os, subprocess, sys

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("GITHUB_TOKEN is not set. Add it to .env and restart the bot.")
    sys.exit(1)
```

## Action: example

Describe what this action does.

```python
# @action: example
result = subprocess.run(["echo", "hello"], capture_output=True, text=True)
print(result.stdout)
```

## How Claude uses this skill

- Claude reads the prose for context and intent.
- Claude extracts and runs `python` blocks marked `# @action: <name>` that match the user's request.
- The `setup` block always runs first.
- Output from the code is returned to the user.
