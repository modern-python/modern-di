---
status: shipped
date: 2026-06-08
slug: scheduled-dep-check
summary: Weekly scheduled dependency-check GitHub Actions workflow.
supersedes: null
superseded_by: null
pr: null
outcome: Weekly scheduled dependency-check workflow (.github/workflows/scheduled.yml).
---

# Scheduled dependency-breakage check

**Date:** 2026-06-08
**Status:** Approved — ready for implementation plan

## Goal

Add a weekly GitHub Actions workflow that runs the project's existing lint and pytest matrix to detect when a newly-released dev or lint dependency (ruff, ty, eof-fixer, pytest stack, typing-extensions) has broken something during the quiet period between PRs. On failure, the workflow opens or updates a single rolling GitHub issue so the maintainer is notified without inbox noise.

## Background

Current CI (`.github/workflows/ci.yml`) runs on every `push` to `main` and on every `pull_request`. It has two jobs: `lint` (Python 3.10, runs `just install lint-ci`) and `pytest` (matrix Python 3.10–3.14, runs `just install` then `just test . --cov=. --cov-report xml`).

Because `just install` is defined as `uv lock --upgrade && uv sync --all-extras --frozen --group lint`, every CI run already pulls the freshest dependency resolution. The lockfile committed to the repo is effectively ignored at CI time.

Implication: PR runs already detect dependency breakage when there *is* a PR. The gap a scheduled run fills is the quiet period — when no PR opens but a new ruff or ty release lands and breaks `lint-ci`, or a new pytest release breaks the test suite. Without a scheduled run, the maintainer first hears about it from the next contributor's red CI.

The package itself has zero runtime dependencies, so only dev/lint deps can produce this kind of breakage.

## Decisions

- **Cadence:** Weekly. Mondays 06:00 UTC.
- **Scope:** Mirror `ci.yml` exactly — full lint + Python 3.10–3.14 matrix. Maximum signal, minimal extra complexity.
- **Code sharing:** Refactor the two jobs out of `ci.yml` into a reusable workflow (`_checks.yml`, triggered by `workflow_call`). Both `ci.yml` (push/PR) and a new `scheduled.yml` (cron) call it. Single source of truth; the two trigger paths can't drift.
- **Failure notification:** Open or update a single rolling GitHub issue labeled `scheduled-failure`, owned by `github-actions[bot]`. First failure opens the issue. Subsequent failures while the issue is open add a comment with the new run URL. Maintainer closes the issue after fixing; the next failure starts a fresh one.
- **Workflow_dispatch failures do NOT report.** The issue logic is guarded by `github.event_name == 'schedule'`, so manual test runs don't self-spam.
- **Tooling:** Use the `gh` CLI (preinstalled on `ubuntu-latest`) for issue management. No third-party action.
- **Permissions:** Default workflow permissions stay read-only; the `report-failure` job alone declares `permissions: contents: read, issues: write`. (`contents: read` is required for `actions/checkout` because declaring any job-level `permissions:` block zeroes out unspecified scopes.)
- **Concurrency:** `scheduled.yml` uses `cancel-in-progress: false` (a queued cron must never cancel another), distinct from `ci.yml`'s cancel-on-new-push behavior.
- **No new top-level skills, deps, or repo conventions.** Only `.github/workflows/` + one helper shell script.

## Repo changes (this PR)

### 1. New reusable workflow `.github/workflows/_checks.yml`

The lint and pytest jobs lift verbatim from today's `ci.yml`. Only the trigger changes.

```yaml
name: checks
on:
  workflow_call: {}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: extractions/setup-just@v2
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
          cache-dependency-glob: "**/pyproject.toml"
      - run: uv python install 3.10
      - run: just install lint-ci

  pytest:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version:
          - "3.10"
          - "3.11"
          - "3.12"
          - "3.13"
          - "3.14"
    steps:
      - uses: actions/checkout@v4
      - uses: extractions/setup-just@v2
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
          cache-dependency-glob: "**/pyproject.toml"
      - run: uv python install ${{ matrix.python-version }}
      - run: just install
      - run: just test . --cov=. --cov-report xml
```

The leading underscore in the filename is a convention signal: "not a top-level entry point."

### 2. Refactored `.github/workflows/ci.yml`

```yaml
name: main
on:
  push:
    branches:
      - main
  pull_request: {}

concurrency:
  group: ${{ github.head_ref || github.run_id }}
  cancel-in-progress: true

jobs:
  checks:
    uses: ./.github/workflows/_checks.yml
```

The original triggers and concurrency behavior are preserved exactly. The jobs are now a single delegating call.

### 3. New `.github/workflows/scheduled.yml`

```yaml
name: scheduled-dep-check
on:
  schedule:
    - cron: "0 6 * * 1"        # Mondays 06:00 UTC
  workflow_dispatch: {}

concurrency:
  group: scheduled-dep-check
  cancel-in-progress: false

jobs:
  checks:
    uses: ./.github/workflows/_checks.yml

  report-failure:
    needs: checks
    if: failure() && github.event_name == 'schedule'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@v4
      - name: Open or update tracking issue
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: bash .github/scripts/report-scheduled-failure.sh
```

### 4. New helper script `.github/scripts/report-scheduled-failure.sh`

Extracted from YAML for readability and so it can be edited and reviewed as a normal shell script.

```bash
#!/usr/bin/env bash
set -euo pipefail

LABEL="scheduled-failure"
TITLE="Scheduled dependency check failed"

# Ensure the label exists (idempotent; --force updates color/description without erroring if present).
gh label create "$LABEL" \
  --color "FBCA04" \
  --description "Weekly dependency check failures" \
  --force

# Find an open issue with our label, if any.
existing=$(gh issue list --label "$LABEL" --state open --json number --jq '.[0].number // empty')

if [ -z "$existing" ]; then
  body=$(printf '%s\n\n%s\n\n%s\n\n%s' \
    "The weekly scheduled dependency check failed." \
    "First failing run: ${RUN_URL}" \
    "Likely cause: a transitive dev or lint dependency (ruff, ty, eof-fixer, pytest, typing-extensions) released a breaking change. Reproduce locally with \`just install\` then \`just lint\` and \`just test\`." \
    "Close this issue once fixed. The next scheduled failure will open a fresh issue.")
  gh issue create --title "$TITLE" --label "$LABEL" --body "$body"
else
  gh issue comment "$existing" --body "Failed again: ${RUN_URL}"
fi
```

Script is checked in as executable. Behavior:

- **First failure ever** (or after the prior issue was closed): opens a new issue with run URL and reproduction instructions.
- **Subsequent failures while issue is open:** comments with the new run URL.
- **Label management is idempotent:** `gh label create --force` updates an existing label without error and creates it if missing.

## What is explicitly out of scope

- **Dependabot, Renovate, or any auto-PR system.** This spec is about detection, not automated fixes.
- **Notifying anywhere outside GitHub** (no Slack, email, webhook). The issue is the signal.
- **Scheduled-only test variants** (e.g., longer fuzz runs, additional Python pre-releases). Scope is "mirror what main CI does."
- **Issue auto-close on success.** If the issue is open and the next scheduled run passes, the issue stays open until the maintainer closes it manually. Auto-close was considered and rejected as overreach — a green run doesn't prove the underlying breakage was actually addressed; it might just mean the upstream dep was reverted.
- **Bisecting which dep caused the breakage.** The issue body points the maintainer at `just install` to reproduce locally; they can `uv lock` diff from there.

## Testing the workflow

**Pre-merge: only `ci.yml` can be exercised.** GitHub requires `workflow_dispatch` workflows to exist on the default branch before they can be dispatched, so `scheduled.yml` itself cannot be triggered from the topic branch. The refactored `ci.yml` does run on the PR via `pull_request`, which fully validates the reusable-workflow extraction.

**Post-merge validations:**

1. **Green path:** Trigger `scheduled-dep-check` from the Actions tab via `workflow_dispatch` (or `gh workflow run scheduled.yml`). Confirm the `checks` job passes and the `report-failure` job is skipped (no issue created — manual dispatch is event-guarded out).
2. **Red path (optional but recommended):** In a follow-up branch, temporarily change `just install lint-ci` to `just install lint-ci && false` in `_checks.yml` AND swap the report-failure guard to `if: failure()` (no event check). Merge that to default branch, dispatch, confirm the issue opens with the right body. Then dispatch again and confirm a comment appears on the same issue rather than a new one. Revert both temporary edits via another PR.

## Success criteria

- Existing `ci.yml` push/PR behavior is unchanged (same matrix, same commands, same concurrency).
- A weekly scheduled run executes on Mondays at 06:00 UTC.
- On scheduled failure, exactly one open tracking issue exists, regardless of how many consecutive failures occur.
- On scheduled failure, the issue (new or existing) contains a clickable link to the failing run.
- Manual `workflow_dispatch` runs never create or update issues.
- `docs.yml` and `publish.yml` are untouched.
