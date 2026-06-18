---
name: release
description: Create pre-releases for all repos with merged PRs in VertexAssetsTech GitHub project 53, then compose the group deployment message
version: 1.0.0
author: nexstox
dependencies: []
env:
  - GITHUB_TOKEN
---

Creates pre-releases for every repository that has merged PRs in the VertexAssetsTech project board (project 53). Automatically determines today's tag, finds the previous tag for each repo, creates pre-releases on GitHub, then outputs a formatted group deployment message ready to paste.

**Author substitution:** always replace `@manh-vv` with `@ethan` in release notes and the group message.

**Tag format:** `v2026.MM.DD-01` (increment suffix `-02`, `-03` if a release already exists today).

## Setup

```python
# @setup
import os, subprocess, sys, json
from urllib import request as urlrequest
from datetime import datetime, timezone

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("GITHUB_TOKEN not set. Add it to .env and restart the bot.")
    sys.exit(1)

ORG = "VertexAssetsTech"
PROJECT_NUMBER = 53

def gh_api(path, method="GET", body=None):
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

def gh_graphql(query):
    data = json.dumps({"query": query}).encode()
    req = urlrequest.Request("https://api.github.com/graphql", data=data, method="POST", headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    })
    with urlrequest.urlopen(req) as resp:
        return json.loads(resp.read())

def replace_author(text):
    return text.replace("@manh-vv", "@ethan")

today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
print(f"Auth OK. Today: {today}")
```

## Action: create

Fetch project board, create pre-releases for each repo, output the group deployment message.

```python
# @action: create

# 1. Fetch merged PRs from project board
query = """
{
  organization(login: "%s") {
    projectV2(number: %d) {
      items(first: 50) {
        nodes {
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
          content {
            ... on PullRequest {
              title
              number
              url
              repository { name }
              author { login }
              mergedAt
              state
            }
          }
        }
      }
    }
  }
}
""" % (ORG, PROJECT_NUMBER)

result = gh_graphql(query)
items = result["data"]["organization"]["projectV2"]["items"]["nodes"]

# 2. Group merged PRs by repo, sorted by mergedAt
from collections import defaultdict
repos = defaultdict(list)
for item in items:
    pr = item.get("content")
    if not pr or pr.get("state") != "MERGED":
        continue
    repo = pr["repository"]["name"]
    repos[repo].append(pr)

for repo in repos:
    repos[repo].sort(key=lambda p: p["mergedAt"])

if not repos:
    print("No merged PRs found in project board.")
    sys.exit(0)

print(f"Found PRs in repos: {', '.join(repos.keys())}")

# 3. For each repo, get latest release and determine new tag
def get_latest_release(repo):
    try:
        releases = gh_api(f"/repos/{ORG}/{repo}/releases?per_page=5")
        if releases:
            return releases[0]["tag_name"]
        return None
    except Exception:
        return None

def next_tag(repo, date_str):
    releases = gh_api(f"/repos/{ORG}/{repo}/releases?per_page=10")
    existing = [r["tag_name"] for r in releases if r["tag_name"].startswith(f"v{date_str}-")]
    if not existing:
        return f"v{date_str}-01"
    suffixes = [int(t.split("-")[-1]) for t in existing]
    return f"v{date_str}-{max(suffixes)+1:02d}"

repo_info = {}
for repo in repos:
    prev_tag = get_latest_release(repo)
    new_tag = next_tag(repo, today)
    repo_info[repo] = {"prev_tag": prev_tag, "new_tag": new_tag}
    print(f"{repo}: {prev_tag} → {new_tag}")

# 4. Create pre-releases
created = {}
for repo, prs in repos.items():
    info = repo_info[repo]
    new_tag = info["new_tag"]
    prev_tag = info["prev_tag"]

    pr_lines = "\n".join(
        replace_author(f"* {pr['title']} by @{pr['author']['login']} in {pr['url']}")
        for pr in prs
    )
    changelog = f"https://github.com/{ORG}/{repo}/compare/{prev_tag}...{new_tag}" if prev_tag else f"https://github.com/{ORG}/{repo}/releases/tag/{new_tag}"
    notes = f"## What's Changed\n{pr_lines}\n\n\n**Full Changelog**: {changelog}"

    release = gh_api(f"/repos/{ORG}/{repo}/releases", method="POST", body={
        "tag_name": new_tag,
        "name": new_tag,
        "body": notes,
        "prerelease": True,
    })
    created[repo] = release["html_url"]
    print(f"Created: {release['html_url']}")

# 5. Output group deployment message
date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
msg_lines = [f"🚀 Staging Deployment {date_label}", ""]

for repo, prs in repos.items():
    msg_lines.append(f"[{repo}]")
    for pr in prs:
        author = replace_author(f"@{pr['author']['login']}")
        msg_lines.append(f"- {pr['title']} by {author} in #{pr['number']}")
    msg_lines.append("")

# Claude: write a 1-2 sentence human summary of what these changes do together, then append it.
print("\n--- GROUP MESSAGE ---")
print("\n".join(msg_lines))
```

## How Claude uses this skill

1. Run the `# @setup` block first to verify auth and set helpers.
2. Run `# @action: create` to execute the full release workflow.
3. After the code output, Claude writes a 1-2 sentence summary of what the changes accomplish and appends it to the group message before showing it to the user.
4. Always replace `@manh-vv` with `@ethan` everywhere.
