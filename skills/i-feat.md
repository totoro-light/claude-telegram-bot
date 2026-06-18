---
name: i-feat
description: Interactive feature dev — checkout, branch, plan with Q&A, implement, open PR
version: 1.0.0
author: nexstox
dependencies:
  - github-pr
env:
  - GITHUB_TOKEN
  - CLAUDE_WORK_DIR
---

Interactive feature development workflow. Invoked as `/i-feat <repo> [branch:<name>] <description>`.

- `<repo>` — repository name resolved under `$CLAUDE_WORK_DIR`
- `branch:<name>` — optional; overrides the default base branch (`main`)
- `<description>` — free-text feature description (the remainder of the message)

Example: `/i-feat my-app branch:develop add JWT authentication`

## Setup

Parse the invocation, validate the repo, and initialise git helpers.

```python
# @setup
import os, subprocess, sys
from pathlib import Path

WORK_DIR     = os.environ.get("CLAUDE_WORK_DIR") or str(Path.cwd())
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Claude fills these from the invocation:
REPO_NAME    = ""       # first word of args
BASE_BRANCH  = "main"   # default; overridden if "branch:<name>" is present in args
FEATURE_DESC = ""       # remaining text after repo name and optional branch override

REPO_PATH = Path(WORK_DIR) / REPO_NAME

if not REPO_PATH.is_dir() or not (REPO_PATH / ".git").exists():
    available = [d.name for d in Path(WORK_DIR).iterdir()
                 if d.is_dir() and (d / ".git").exists()]
    print(f"Repo '{REPO_NAME}' not found under {WORK_DIR}")
    print(f"Available repos: {', '.join(available) or 'none'}")
    sys.exit(1)

def git(*args, cwd=REPO_PATH):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        print(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
        sys.exit(1)
    return r.stdout.strip()

print(f"Repo    : {REPO_PATH}")
print(f"Base    : {BASE_BRANCH}")
print(f"Feature : {FEATURE_DESC}")
```

## Action: checkout-and-branch

Fetch, checkout the base branch, pull latest, and create the feature branch.

```python
# @action: checkout-and-branch
# Claude fills in:
BRANCH_SLUG = ""                  # kebab-case slug derived from FEATURE_DESC (max 50 chars)
BRANCH_NAME = f"feat/{BRANCH_SLUG}"

dirty = git("status", "--short")
if dirty:
    git("stash", "push", "-m", "i-feat: auto-stash before checkout")

git("fetch", "origin")
git("checkout", BASE_BRANCH)
git("pull", "origin", BASE_BRANCH)
git("checkout", "-b", BRANCH_NAME)
print(f"Branch ready: {BRANCH_NAME}")
```

## Action: create-planning-doc

Write `docs/planning_<slug>.md` in the repo, populated from the Q&A session.

```python
# @action: create-planning-doc
# Claude fills in all values from the Q&A:
FEATURE_SLUG = ""    # same slug used in BRANCH_NAME
ANSWERS      = []    # list of {"question": str, "answer": str}
DECISIONS    = []    # list of {"decision": str, "choice": str, "tradeoff": str}

docs_dir = REPO_PATH / "docs"
docs_dir.mkdir(exist_ok=True)
plan_path = docs_dir / f"planning_{FEATURE_SLUG}.md"

lines = [
    f"# Feature Plan: {FEATURE_DESC}",
    "",
    f"**Branch:** `{BRANCH_NAME}`  ",
    f"**Base:** `{BASE_BRANCH}`",
    "",
    "## Requirements",
    "",
]
for item in ANSWERS:
    lines.append(f"**{item['question']}**  ")
    lines.append(f"{item['answer']}")
    lines.append("")

if DECISIONS:
    lines += ["## Key Decisions", ""]
    for d in DECISIONS:
        lines.append(f"### {d['decision']}")
        lines.append(f"- **Choice:** {d['choice']}")
        lines.append(f"- **Tradeoff:** {d['tradeoff']}")
        lines.append("")

plan_path.write_text("\n".join(lines))
print(f"Created: {plan_path.relative_to(REPO_PATH)}")
```

## Action: commit-plan

Commit the planning doc as the first commit on the feature branch and push to remote.

```python
# @action: commit-plan
git("add", f"docs/planning_{FEATURE_SLUG}.md")
git("commit", "-m", f"docs: planning doc for {FEATURE_SLUG}")
git("push", "-u", "origin", BRANCH_NAME)
print(f"Planning doc committed and pushed on {BRANCH_NAME}")
```

## How Claude uses this skill

**Step 1 — Parse and setup**

Fill in `REPO_NAME`, `BASE_BRANCH` (default `main`; look for `branch:<name>` anywhere in args), and `FEATURE_DESC`. Run the `setup` block to validate the repo, then run `checkout-and-branch` (derive `BRANCH_SLUG` as a lowercase kebab slug of `FEATURE_DESC`, max 50 chars).

**Step 2 — Clarifying questions (one at a time)**

Ask the user questions to fully understand the requirement. Ask exactly one question, wait for the answer, then ask the next. Never ask two questions in the same message. Cover these areas, skipping any that are already obvious from context:

- Exact scope and boundaries — what is in vs out
- Acceptance criteria or definition of done
- Existing code patterns or files to follow for consistency
- Key edge cases or failure modes to handle
- External dependencies, environment variables, or API changes needed

Stop at three to six questions once you have enough to write a complete plan.

**Step 3 — Decision walkthrough (one at a time)**

Identify the key architectural or design decisions. For each one:
1. Name the decision
2. Present two or three concrete options
3. State the tradeoff for each option clearly
4. Wait for the user's choice before moving to the next decision

**Step 4 — Confirm the plan**

Summarise everything: feature scope, captured requirements, and chosen decisions. Ask for explicit confirmation ("Looks good, proceed" or similar) before doing anything further.

**Step 5 — Create and commit the planning doc**

Run `create-planning-doc` (fill in `FEATURE_SLUG`, `ANSWERS` from step 2, `DECISIONS` from step 3), then run `commit-plan`.

**Step 6 — Implement**

Work in `REPO_PATH`. Follow the plan. Commit logical units of work with descriptive messages.

**Step 7 — Open PR**

Use the `github-pr` skill's `create` action, operating from `REPO_PATH`, to open a pull request from `BRANCH_NAME` → `BASE_BRANCH`. Link the planning doc in the PR body.
