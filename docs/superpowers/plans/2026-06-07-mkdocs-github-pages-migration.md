# MkDocs to GitHub Pages Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move modern-di documentation hosting from Read the Docs to GitHub Pages at `https://modern-di.modern-python.org`, with a flat URL structure (no `/latest/` prefix), built and deployed by a GitHub Actions workflow.

**Architecture:** A new `.github/workflows/docs.yml` builds the existing MkDocs Material site and force-pushes it to a `gh-pages` branch via `mkdocs gh-deploy --force`. GitHub Pages is configured (out-of-repo) to serve from `gh-pages` at the custom domain. The single in-code reference to the docs URL (`modern_di/errors.py`) is updated to drop `/latest/`. A `Justfile` target provides a local-deploy escape hatch. `.readthedocs.yaml` is left in place as a passive fallback and removed in a separate follow-up PR.

**Tech Stack:** MkDocs 1.6.x + mkdocs-material (already configured in `mkdocs.yml` and `docs/requirements.txt`); GitHub Actions; `uvx` for local mkdocs invocation (project does not depend on mkdocs in its uv lockfile).

**Reference spec:** `docs/superpowers/specs/2026-06-07-mkdocs-github-pages-migration-design.md`

---

## Pre-flight: Working tree state

Before starting, the working tree should have these **uncommitted** edits (left over from the spec session — they are intentionally rolled into the migration PR rather than committed separately):

- `README.md`: line 35 contains `https://modern-di.modern-python.org` (was `.online` on disk before the spec session — `.org` is the desired final state)
- `pyproject.toml`: line 30 contains `docs = "https://modern-di.modern-python.org"`
- `mkdocs.yml`: line 2 contains `site_url: https://modern-di.modern-python.org`
- `modern_di/errors.py`: line 32 contains `https://modern-di.modern-python.org/latest/troubleshooting/duplicate-type-error/` (the `/latest/` still needs to be dropped — Task 2)

Verify with:

```bash
git status --short
```

Expected output:

```
 M README.md
 M mkdocs.yml
 M modern_di/errors.py
 M pyproject.toml
```

If any of those four files are unmodified, stop and resolve before continuing — the plan assumes those edits are already present in the working tree.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `.github/workflows/docs.yml` | **Create** | Build and deploy docs to `gh-pages` on push to `main` |
| `Justfile` | Modify | Add `docs-deploy` target for local rescue deploys |
| `modern_di/errors.py` | Modify | Drop `/latest/` from the troubleshooting URL |
| `README.md` | Modify (already done in working tree) | Documentation link rewritten to `.org` |
| `pyproject.toml` | Modify (already done in working tree) | `[project.urls].docs` rewritten to `.org` |
| `mkdocs.yml` | Modify (already done in working tree) | Add `site_url` |
| `.readthedocs.yaml` | Untouched | Left in place; removed in a follow-up PR |
| `docs/context7.json` | Untouched | Updated separately via the context7 dashboard |

---

## Task 1: Create the feature branch

**Files:**
- None modified in this task

- [ ] **Step 1: Confirm clean status apart from the four expected edits**

```bash
git status --short
```

Expected:

```
 M README.md
 M mkdocs.yml
 M modern_di/errors.py
 M pyproject.toml
```

If anything else appears (other untracked files, additional modifications), stop and investigate before continuing.

- [ ] **Step 2: Create and switch to the feature branch**

```bash
git checkout -b migrate-docs-to-github-pages
```

Expected: `Switched to a new branch 'migrate-docs-to-github-pages'`

- [ ] **Step 3: Confirm branch is set**

```bash
git branch --show-current
```

Expected: `migrate-docs-to-github-pages`

---

## Task 2: Drop `/latest/` from the errors.py troubleshooting URL

**Files:**
- Modify: `modern_di/errors.py:32`

- [ ] **Step 1: Inspect current state**

```bash
grep -n "duplicate-type-error" modern_di/errors.py
```

Expected:

```
32:    "See https://modern-di.modern-python.org/latest/troubleshooting/duplicate-type-error/ for more details"
```

- [ ] **Step 2: Apply the edit**

Replace the single matching line in `modern_di/errors.py`:

Old:

```python
    "See https://modern-di.modern-python.org/latest/troubleshooting/duplicate-type-error/ for more details"
```

New:

```python
    "See https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ for more details"
```

- [ ] **Step 3: Verify edit**

```bash
grep -n "duplicate-type-error" modern_di/errors.py
```

Expected:

```
32:    "See https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ for more details"
```

(No `/latest/` in the URL.)

- [ ] **Step 4: Confirm no other `/latest/` references remain**

```bash
grep -rn "modern-python.org/latest" --include="*.py" --include="*.md" --include="*.toml" --include="*.yml" --include="*.yaml" .
```

Expected: no output.

- [ ] **Step 5: Run the existing test suite to confirm no test asserts on the old URL**

```bash
just test
```

Expected: all tests pass. If a test fails because it asserted on the old URL string, update the test in this same task (none expected based on pre-plan grep, but handle if encountered).

---

## Task 3: Add `docs-deploy` target to the Justfile

**Files:**
- Modify: `Justfile` (append new target)

- [ ] **Step 1: Inspect current Justfile**

```bash
cat Justfile
```

Expected: existing targets `default`, `install`, `lint`, `lint-ci`, `test`, `test-branch`, `publish`.

- [ ] **Step 2: Append the new target**

Append to the end of `Justfile`:

```just

docs-deploy:
    uvx --with-requirements docs/requirements.txt mkdocs gh-deploy --force
```

(Leading blank line separates the new target from `publish`. Uses `uvx --with-requirements` because the project doesn't include mkdocs in its uv lockfile — matches how the user would run mkdocs locally without polluting project deps.)

- [ ] **Step 3: Verify Justfile syntax**

```bash
just --list
```

Expected: lists existing targets plus `docs-deploy`.

- [ ] **Step 4: Dry-run target listing**

```bash
just --evaluate docs-deploy 2>&1 || just --show docs-deploy
```

Expected: shows the recipe body without executing. (Do not run `just docs-deploy` here — it would actually push to `gh-pages`, which we don't want until after the workflow has run on `main`.)

---

## Task 4: Create the GitHub Pages deploy workflow

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Confirm the workflows directory exists**

```bash
ls .github/workflows/
```

Expected: lists existing workflows (`ci.yml`, `publish.yml`).

- [ ] **Step 2: Create the workflow file**

Create `.github/workflows/docs.yml` with this exact content:

```yaml
name: Deploy docs
on:
  push:
    branches: [main]
    paths:
      - "docs/**"
      - "mkdocs.yml"
      - "docs/requirements.txt"
      - ".github/workflows/docs.yml"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r docs/requirements.txt
      - run: mkdocs gh-deploy --force
```

Notes baked into the design:

- `fetch-depth: 0` — required by `mkdocs gh-deploy` to push to `gh-pages` from current HEAD context.
- `--force` — overwrites the `gh-pages` branch each run (single rolling version).
- `workflow_dispatch` — lets you trigger manually from the GitHub UI if needed.
- `contents: write` — required to push to `gh-pages` from the default `GITHUB_TOKEN`.
- The `paths:` filter listing `docs/requirements.txt` is redundant with `docs/**` but kept for visibility.

- [ ] **Step 3: Validate the YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs.yml'))"
```

Expected: no output, exit code 0.

---

## Task 5: Local build verification

**Files:**
- None modified in this task

- [ ] **Step 1: Build the site locally with `--strict`**

```bash
uvx --with-requirements docs/requirements.txt mkdocs build --strict
```

Expected: ends with `INFO - Documentation built in N seconds`. No warnings about missing pages, broken links, or invalid config (any warning becomes an error under `--strict`).

If the build fails:

- Read the error. Common issues: a broken markdown link, an undefined nav entry, or a config typo.
- Fix in place. Do not proceed to commit until `--strict` build is green.

- [ ] **Step 2: Confirm `site/` was produced**

```bash
ls site/index.html
```

Expected: `site/index.html` exists.

- [ ] **Step 3: Clean up the build artifact**

```bash
rm -rf site/
```

`site/` is gitignored already, but removing it keeps the working tree tidy.

```bash
grep -E "^site/?$" .gitignore || echo "WARNING: site/ not in .gitignore"
```

Expected: prints `site/` (or no output if absent — see warning). If absent, add `site/` to `.gitignore` before committing.

---

## Task 6: Commit all repo changes

**Files:**
- All four pre-existing edits + the three new/changed files from Tasks 2–4

- [ ] **Step 1: Review the full diff**

```bash
git status --short && echo "---" && git diff --stat
```

Expected `git status --short` output:

```
 M Justfile
 M README.md
 M mkdocs.yml
 M modern_di/errors.py
 M pyproject.toml
?? .github/workflows/docs.yml
```

Expected `git diff --stat`: shows changes in `Justfile`, `README.md`, `mkdocs.yml`, `modern_di/errors.py`, `pyproject.toml`. (`docs.yml` is untracked and not in `git diff` output yet.)

- [ ] **Step 2: Stage everything**

```bash
git add .github/workflows/docs.yml Justfile README.md mkdocs.yml modern_di/errors.py pyproject.toml
```

- [ ] **Step 3: Verify staging**

```bash
git status --short
```

Expected:

```
A  .github/workflows/docs.yml
M  Justfile
M  README.md
M  mkdocs.yml
M  modern_di/errors.py
M  pyproject.toml
```

(All capital letters in the first column = staged.)

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
Migrate docs hosting from Read the Docs to GitHub Pages

Add docs deploy workflow that runs mkdocs gh-deploy on push to main,
drop the /latest/ prefix from the in-error troubleshooting URL (GH Pages
serves at root), add a Justfile escape hatch for local deploys, and
finalize the .org subdomain rename.

.readthedocs.yaml is left in place as a passive fallback; a follow-up
PR will remove it once the new setup is verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds with all six files included.

- [ ] **Step 5: Verify the commit**

```bash
git log -1 --stat
```

Expected: shows the new commit with all six files changed.

---

## Task 7: Push the branch and open a PR

**Files:**
- None modified

- [ ] **Step 1: Push the branch**

```bash
git push -u origin migrate-docs-to-github-pages
```

Expected: branch pushed; GitHub returns a "create PR" URL in stderr.

- [ ] **Step 2: Open a PR via the GitHub CLI**

```bash
gh pr create --title "Migrate docs hosting from Read the Docs to GitHub Pages" --body "$(cat <<'EOF'
## Summary

- Adds `.github/workflows/docs.yml` which builds the MkDocs Material site and force-pushes it to `gh-pages` on every push to `main` that touches docs sources.
- Drops `/latest/` from the troubleshooting URL embedded in `modern_di/errors.py` (GitHub Pages serves at root; no version prefix).
- Adds a `docs-deploy` target to the `Justfile` as a local rescue path (uses `uvx --with-requirements docs/requirements.txt`).
- Finalizes the `.online` → `.org` subdomain rename across `README.md`, `pyproject.toml`, `mkdocs.yml`, and `modern_di/errors.py`.
- Leaves `.readthedocs.yaml` in place; a follow-up PR will remove it once the new setup is verified.

See full design rationale in `docs/superpowers/specs/2026-06-07-mkdocs-github-pages-migration-design.md`.

## Post-merge steps (manual)

1. GitHub repo Settings → Pages: set source to branch `gh-pages` / root, set custom domain to `modern-di.modern-python.org`, enable Enforce HTTPS once provisioned.
2. DNS at registrar: replace the `modern-di` CNAME (currently pointing at RTD) with a CNAME pointing to `modern-python.github.io.`.
3. Wait for DNS + Let's Encrypt (typically 5–30 minutes).
4. Verify: `curl -I https://modern-di.modern-python.org/` returns 200 with a valid cert.

## Test plan

- [ ] Workflow run on this PR or after merge to main completes green.
- [ ] `gh-pages` branch is created in the repo and contains the built site.
- [ ] After DNS swap, `https://modern-di.modern-python.org/` serves the docs.
- [ ] The troubleshooting URL emitted by `PROVIDER_DUPLICATE_TYPE_ERROR` resolves correctly.
- [ ] `just docs-deploy` runs successfully if invoked locally (only to be used as a rescue path).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: prints the PR URL.

- [ ] **Step 3: Record the PR URL**

The PR URL is printed by `gh pr create`. Save it for reference when performing post-merge steps.

---

## Task 8: Merge the PR

**Files:**
- None

This step is performed by the user. The plan executor pauses here and surfaces the PR URL.

- [ ] **Step 1: User reviews the PR**

User opens the PR URL in a browser, reviews the diff (six files), and merges. Merge method (squash vs merge commit) is at user discretion — the repo history shows both.

- [ ] **Step 2: After merge, confirm the workflow runs**

Wait ~30 seconds for the post-merge workflow to start, then:

```bash
git checkout main && git pull
gh run list --workflow=docs.yml --limit=1
```

Expected: a workflow run is `in_progress` or `completed`.

- [ ] **Step 3: Wait for the run to finish**

```bash
gh run watch
```

(Pick the most recent run if prompted.) Expected: ends with `completed | success`.

If the run fails: read the logs via `gh run view --log-failed` and fix forward in a new commit on `main`.

- [ ] **Step 4: Confirm `gh-pages` branch was created**

```bash
git ls-remote --heads origin gh-pages
```

Expected: a single SHA is printed (the branch exists on the remote).

- [ ] **Step 5: Smoke-check the github.io URL**

```bash
curl -sI https://modern-python.github.io/modern-di/ | head -5
```

Expected: `HTTP/2 200` and HTML content type. (This URL works regardless of DNS state; it confirms the build succeeded and Pages is serving from `gh-pages`.)

If this returns 404, give it another minute — Pages takes a moment to pick up a new branch the first time.

---

## Task 9: Add `docs/CNAME` so the custom domain survives `gh-deploy --force`

**Files:**
- Create: `docs/CNAME`

`mkdocs gh-deploy --force` wipes the `gh-pages` branch on every run. If GitHub Pages were configured first, the `CNAME` file GitHub writes to `gh-pages` would be lost on the next workflow run. The canonical fix is to commit a `CNAME` file in `docs/` — MkDocs copies files from `docs/` into the build output, so `docs/CNAME` ends up at the root of the deployed site as `CNAME` on every deploy.

This task is performed on `main` after Task 8.

- [ ] **Step 1: Switch back to main and pull**

```bash
git checkout main && git pull
```

- [ ] **Step 2: Create `docs/CNAME` with the custom domain**

Create `docs/CNAME` containing exactly one line:

```
modern-di.modern-python.org
```

No trailing whitespace, no other characters, no surrounding quotes.

- [ ] **Step 3: Confirm `docs/CNAME` is not excluded from the mkdocs build**

```bash
grep -E "exclude_docs|CNAME" mkdocs.yml
```

Expected: no output. (`mkdocs.yml` has no `exclude_docs` directive, so this file will be copied through to the site root.)

- [ ] **Step 4: Verify locally that the file ends up at site root**

```bash
uvx --with-requirements docs/requirements.txt mkdocs build --strict && cat site/CNAME && rm -rf site/
```

Expected: prints `modern-di.modern-python.org`.

- [ ] **Step 5: Commit and push**

```bash
git add docs/CNAME && git commit -m "$(cat <<'EOF'
Preserve GitHub Pages custom domain across gh-deploy runs

mkdocs gh-deploy --force wipes the gh-pages branch each run. Without a
CNAME file inside the build output, the custom-domain CNAME GitHub Pages
writes to gh-pages would be lost on every deploy. docs/CNAME is copied
into the build by MkDocs, so the custom domain survives.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" && git push
```

- [ ] **Step 6: Wait for the workflow to redeploy**

```bash
gh run watch
```

Expected: completes successfully.

- [ ] **Step 7: Confirm the deployed CNAME on `gh-pages`**

```bash
curl -s https://modern-python.github.io/modern-di/CNAME
```

Expected: `modern-di.modern-python.org`

(GitHub Pages serves a file named `CNAME` if present at site root, but it's not the same as the *active* custom domain — that's set in Pages settings in the next task. This step just confirms the file is in place.)

---

## Task 10: Configure GitHub Pages custom domain (user-side)

**Files:**
- None in the repo

This step is performed by the user via the GitHub web UI. Because `docs/CNAME` already exists (Task 9), GitHub will recognize the existing custom-domain marker and not need to write a separate file to `gh-pages`.

- [ ] **Step 1: Navigate to repo Settings → Pages**

URL: `https://github.com/modern-python/modern-di/settings/pages`

- [ ] **Step 2: Set the source (if not already set)**

- Source: **Deploy from a branch**
- Branch: **`gh-pages`** / **`/ (root)`**
- Click **Save** if any changes.

(This may already be set from Task 8's first deploy; if so, leave as-is.)

- [ ] **Step 3: Set the custom domain**

- Custom domain field: `modern-di.modern-python.org`
- Click **Save**.

GitHub will begin DNS verification. Expect a warning about an unverified domain until Task 11 (DNS swap) is complete — that warning is correct and resolves itself.

- [ ] **Step 4: Leave "Enforce HTTPS" unchecked for now**

The Enforce HTTPS checkbox is greyed out until the Let's Encrypt cert is provisioned. That happens automatically a few minutes after Task 11's DNS change propagates.

---

## Task 11: Update DNS to point the subdomain at GitHub Pages

**Files:**
- None in the repo

This step is performed by the user at the DNS registrar.

- [ ] **Step 1: Record the current CNAME (for rollback)**

```bash
dig modern-di.modern-python.org CNAME +short
```

Expected: returns the current RTD target (something ending in `.readthedocs.io.` or RTD's CDN host). Note it down in case you need to roll back.

- [ ] **Step 2: At the registrar, replace the CNAME**

In the DNS management UI for `modern-python.org`:

- Find the existing CNAME record with host `modern-di` (or `modern-di.modern-python.org`).
- Change its value to: `modern-python.github.io.` (note the trailing dot if the UI uses FQDN; some UIs add it automatically).
- TTL: Automatic or 1 hour.
- Save.

- [ ] **Step 3: Wait for DNS to propagate, then verify**

```bash
dig modern-di.modern-python.org CNAME +short
```

Expected (eventually, may take a few minutes): `modern-python.github.io.`

If the old value persists for more than 10 minutes, the registrar may have caching — try `dig @1.1.1.1 modern-di.modern-python.org CNAME +short` to bypass the local resolver.

- [ ] **Step 4: Confirm GitHub recognizes the DNS**

Refresh `https://github.com/modern-python/modern-di/settings/pages`. Expected: green checkmark next to the custom domain. The "Enforce HTTPS" checkbox becomes available after the certificate is provisioned (a few minutes more).

- [ ] **Step 5: Enable Enforce HTTPS**

Check the **Enforce HTTPS** box. Click Save.

---

## Task 12: End-to-end verification

**Files:**
- None

- [ ] **Step 1: HTTPS works with a valid cert**

```bash
curl -sI https://modern-di.modern-python.org/ | head -3
```

Expected:

```
HTTP/2 200
content-type: text/html; charset=utf-8
...
```

- [ ] **Step 2: The previously-`/latest/`-prefixed URL now resolves at root**

```bash
curl -sI https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ | head -1
```

Expected: `HTTP/2 200`

- [ ] **Step 3: Sanity-load the homepage in a browser**

Open `https://modern-di.modern-python.org/` and click through a few nav entries (Introduction → About DI, Providers → Factories). Make sure assets (CSS, search) load.

- [ ] **Step 4: Run the project's own error path to confirm the in-code URL is live**

The PROVIDER_DUPLICATE_TYPE_ERROR message references the new URL. A quick smoke test in a Python REPL:

```bash
uv run python -c "from modern_di import errors; print(errors.PROVIDER_DUPLICATE_TYPE_ERROR)"
```

Expected: prints the error template, with `https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/` in it (no `/latest/`).

- [ ] **Step 5: Verify RTD fallback still works**

```bash
curl -sI https://modern-di.readthedocs.io/ | head -1
```

Expected: `HTTP/2 200` or a redirect (302/301). RTD keeps building the docs at its native URL; this confirms the fallback is intact for any external links still pointing at it.

---

## Task 13: Rollback procedure (reference only — do not execute unless needed)

If at any point after the DNS swap the site is broken and you need to revert quickly:

- [ ] **Step 1: Revert DNS**

At the registrar, change the `modern-di` CNAME back to the old RTD target (recorded in Task 11 Step 1). Wait 5–10 minutes for DNS to repropagate.

- [ ] **Step 2: (Optional) Remove GitHub Pages custom domain**

GitHub repo Settings → Pages → Custom domain → clear the field and Save.

- [ ] **Step 3: (Optional) Delete the `gh-pages` branch if reverting permanently**

```bash
git push origin --delete gh-pages
```

And revert the migration PR.

RTD's `.readthedocs.yaml` is untouched throughout this plan, so RTD continues serving its own URL and (after DNS revert) the custom domain too.

---

## Follow-up work (separate PRs — do not include in this one)

These items are explicitly out of scope for this plan, per the spec:

- **Delete `.readthedocs.yaml`** — separate PR once the new setup has been stable for a while.
- **Update `docs/context7.json`** — re-index docs on context7 at the new domain, then update the source URL in this file.
