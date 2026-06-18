---
name: github-pr
description: Create, list, review, merge, and manage GitHub pull requests
version: 1.0.0
author: nexstox
dependencies: []
env:
  - GITHUB_TOKEN
---

Manage GitHub pull requests for the current repo. Detects the repo from `git remote` automatically. Uses `gh` CLI when available, falls back to GitHub API via `GITHUB_TOKEN`.

## Setup

Always run this block first to resolve the repo and verify auth.

```python
# @setup
import os, subprocess, sys, json
from urllib import request as urlrequest

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("GITHUB_TOKEN not set. Add it to .env and restart the bot.")
    sys.exit(1)

def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True)
    return r.stdout.strip()

def api(path, method="GET", body=None):
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urlrequest.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urlrequest.urlopen(req) as resp:
        return json.loads(resp.read())

remote = git("remote", "get-url", "origin")
# normalise: https://github.com/owner/repo.git or git@github.com:owner/repo.git
repo = remote.replace("https://github.com/", "").replace("git@github.com:", "").removesuffix(".git")
branch = git("branch", "--show-current")
print(f"Repo: {repo}  Branch: {branch}")
```

## Action: list

Show all open pull requests.

```python
# @action: list
prs = api(f"/repos/{repo}/pulls?state=open&per_page=20")
if not prs:
    print("No open pull requests.")
else:
    for pr in prs:
        print(f"#{pr['number']}  {pr['title']}  ({pr['head']['ref']} → {pr['base']['ref']})  {pr['html_url']}")
```

## Action: create

Create a PR from the current branch. Drafts title and body from recent commits.

```python
# @action: create
base = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").replace("origin/", "") or "main"
log = git("log", f"origin/{base}..HEAD", "--oneline")
if not log:
    print("No commits ahead of base branch. Nothing to open a PR for.")
    sys.exit(0)

# Claude: draft a concise PR title (≤70 chars) and markdown body from the log above,
# then fill in `title` and `body` below before running the API call.
title = ""   # Claude fills this in
body  = ""   # Claude fills this in

pr = api(f"/repos/{repo}/pulls", method="POST", body={
    "title": title, "body": body, "head": branch, "base": base
})
print(f"PR created: {pr['html_url']}")
```

## Action: view [number]

Show details of a PR. If no number is given, use the PR for the current branch.

```python
# @action: view
pr_number = None  # Claude sets this from the user's argument, or detects from branch below

if pr_number is None:
    prs = api(f"/repos/{repo}/pulls?head={repo.split('/')[0]}:{branch}")
    if prs:
        pr_number = prs[0]["number"]
    else:
        print("No open PR found for the current branch.")
        sys.exit(0)

pr = api(f"/repos/{repo}/pulls/{pr_number}")
print(f"#{pr['number']} {pr['title']}")
print(f"State: {pr['state']}  Mergeable: {pr.get('mergeable')}")
print(f"By: {pr['user']['login']}  {pr['created_at'][:10]}")
print(f"URL: {pr['html_url']}")
print(f"\n{pr['body'] or '(no description)'}")
```

## Action: merge [number]

Squash-merge a PR after confirming with the user.

```python
# @action: merge
pr_number = None  # Claude sets this from the user's argument

pr = api(f"/repos/{repo}/pulls/{pr_number}")
print(f"About to squash-merge: #{pr['number']} {pr['title']}")
# Claude: confirm with the user before running the merge call below.

result = api(f"/repos/{repo}/pulls/{pr_number}/merge", method="PUT", body={
    "merge_method": "squash",
    "commit_title": f"{pr['title']} (#{pr_number})",
})
print(result.get("message", "Merged."))
```

## Action: close [number]

Close a PR without merging.

```python
# @action: close
pr_number = None  # Claude sets this from the user's argument

api(f"/repos/{repo}/pulls/{pr_number}", method="PATCH", body={"state": "closed"})
print(f"PR #{pr_number} closed.")
```

## How Claude uses this skill

1. Run the `# @setup` block first.
2. Match the user's request to an action by name.
3. Fill in any `# Claude sets this` placeholders from the user's message.
4. For `create`, draft the PR title and body from the commit log, then run the API call.
5. For `merge`, always confirm with the user before executing.
