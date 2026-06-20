---
status: shipped
date: 2026-06-08
slug: scheduled-dep-check
spec: design.md
pr: null
---

# Scheduled Dependency-Breakage Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly GitHub Actions workflow that runs the existing lint + pytest matrix and opens a rolling tracking issue on failure, so dev/lint dependency regressions are caught between PRs.

**Architecture:** Refactor the two jobs in `ci.yml` into a `workflow_call`-triggered reusable workflow (`_checks.yml`). Both `ci.yml` (push/PR) and a new `scheduled.yml` (cron + dispatch) call it. On scheduled failure only, a separate job runs a bash helper that uses the `gh` CLI to maintain a single rolling tracking issue.

**Tech Stack:** GitHub Actions reusable workflows (`workflow_call`), `gh` CLI (preinstalled on `ubuntu-latest`), bash. No new repo dependencies.

**Spec:** `planning/specs/2026-06-08-scheduled-dep-check-design.md`

---

### Task 1: Extract reusable workflow `_checks.yml` and thin out `ci.yml`

**Goal:** Preserve today's push/PR behavior exactly while moving the jobs to a reusable workflow. After this task, `ci.yml` is a one-job delegator and all real work lives in `_checks.yml`. No scheduling logic yet.

**Files:**
- Create: `.github/workflows/_checks.yml`
- Modify: `.github/workflows/ci.yml` (full rewrite — was 47 lines, becomes 13)

**Pre-flight check — read the current `ci.yml` before editing:**

- [ ] **Step 1: Read the current `ci.yml`**

Run: `cat .github/workflows/ci.yml`

Confirm it matches what this task assumes (lines 14–46 are the lint + pytest jobs that get lifted verbatim). If `ci.yml` has been modified since this plan was written, stop and re-sync the plan with the spec author.

- [ ] **Step 2: Create `.github/workflows/_checks.yml`**

File contents:

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

Notes:
- `on: workflow_call: {}` is the trigger that allows other workflows to invoke this one with `uses: ./.github/workflows/_checks.yml`.
- Action pins (`@v4`, `@v2`, `@v3`) match today's `ci.yml` exactly — do not bump them in this task.
- Concurrency intentionally **omitted** here; the calling workflow controls concurrency.

- [ ] **Step 3: Rewrite `.github/workflows/ci.yml`**

Replace the entire file (47 lines → 13 lines) with:

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

Notes:
- Triggers and concurrency are preserved verbatim from the current `ci.yml`.
- `uses: ./.github/workflows/_checks.yml` — the leading `./` is mandatory for local reusable workflows. `actions/checkout` is NOT needed here; the called workflow does its own checkout.

- [ ] **Step 4: Validate YAML syntax locally**

Run (one of, in order of preference):

```bash
# Option A: actionlint if installed (best)
actionlint .github/workflows/_checks.yml .github/workflows/ci.yml

# Option B: basic YAML validity if actionlint is not installed
python -c "import yaml; yaml.safe_load(open('.github/workflows/_checks.yml')); yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"
```

Expected: `actionlint` prints nothing (success), or the python check prints `ok`.

If actionlint reports an `SC` (shellcheck) finding, ignore — there are no `run:` shell scripts complex enough to matter here.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/_checks.yml .github/workflows/ci.yml
git commit -m "Extract CI lint and pytest jobs into reusable workflow

ci.yml now delegates to a workflow_call-triggered _checks.yml.
No behavior change for push/PR runs; same matrix, same commands,
same concurrency.

Prepares the ground for a sibling scheduled workflow to reuse the
same jobs."
```

- [ ] **Step 6: Validate end-to-end on GitHub (push branch and observe)**

Push the branch and open a draft PR (or just push if working on a topic branch; PRs trigger `pull_request`).

```bash
git push -u origin "$(git branch --show-current)"
```

Open the GitHub Actions tab and confirm:
- A workflow run named **main** appears.
- It has one job called **checks** that fans out into the same `lint` + `pytest (3.10..3.14)` jobs as before.
- All matrix jobs pass.

If any job fails, the refactor regressed something — diff against the pre-refactor `ci.yml`. Do not proceed to Task 2 until this is green.

---

### Task 2: Add the issue-reporting helper script

**Goal:** Create the bash script that the scheduled workflow's `report-failure` job will run. Script is standalone and can be syntax-checked locally; full behavior is exercised in Task 4.

**Files:**
- Create: `.github/scripts/report-scheduled-failure.sh` (new directory `.github/scripts/`)

- [ ] **Step 1: Create the directory and write the script**

```bash
mkdir -p .github/scripts
```

Then create `.github/scripts/report-scheduled-failure.sh` with these exact contents:

```bash
#!/usr/bin/env bash
set -euo pipefail

LABEL="scheduled-failure"
TITLE="Scheduled dependency check failed"

# Ensure the label exists. --force makes this idempotent: creates if absent,
# updates color/description without error if present.
gh label create "$LABEL" \
  --color "FBCA04" \
  --description "Weekly dependency check failures" \
  --force

# Find an open issue with our label, if any. --jq '.[0].number // empty'
# yields the first number or an empty string when there are no matches.
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

Behavior:
- Reads `RUN_URL` and `GH_TOKEN` from the environment — both are set by `scheduled.yml` (added in Task 3).
- Idempotent label management — safe to run on a repo that doesn't have the label yet.
- First failure → opens new issue. Subsequent failures while open → comments with the run URL.

- [ ] **Step 2: Mark it executable**

```bash
chmod +x .github/scripts/report-scheduled-failure.sh
```

Git records the file mode; this is necessary so the workflow's `bash .github/scripts/...` invocation works even without an explicit `bash` prefix in the future. (Today we invoke with `bash`, so this is belt-and-suspenders.)

- [ ] **Step 3: Syntax-check the script locally**

Run (one of, in order of preference):

```bash
# Option A: shellcheck if installed (best)
shellcheck .github/scripts/report-scheduled-failure.sh

# Option B: bash syntax check only (always available)
bash -n .github/scripts/report-scheduled-failure.sh && echo "ok"
```

Expected: `shellcheck` exits 0 with no output, or `bash -n` prints `ok`.

If `shellcheck` flags `SC2086` (unquoted `$existing`), confirm that line is `gh issue comment "$existing"` — already quoted — and ignore. If it flags anything else, fix it before committing.

- [ ] **Step 4: Commit**

```bash
git add .github/scripts/report-scheduled-failure.sh
git commit -m "Add helper script to file rolling issue on scheduled CI failure

Maintains a single open issue labeled scheduled-failure: opens one
on first failure, comments on subsequent failures while open.
Idempotently creates the label with gh label create --force.

Consumed by scheduled.yml in a later commit."
```

---

### Task 3: Add the scheduled workflow `scheduled.yml`

**Goal:** Wire up the weekly cron + manual dispatch trigger, delegate the actual checks to `_checks.yml`, and run the helper script on failure (scheduled events only).

**Files:**
- Create: `.github/workflows/scheduled.yml`

- [ ] **Step 1: Create `.github/workflows/scheduled.yml`**

File contents:

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
      issues: write
    steps:
      - uses: actions/checkout@v4
      - name: Open or update tracking issue
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: bash .github/scripts/report-scheduled-failure.sh
```

Critical details — do not change without re-reading the spec:
- `cron: "0 6 * * 1"` — Mondays 06:00 UTC. GitHub may delay scheduled runs by several minutes during high load; that's expected and unchanged from any other GH Actions cron.
- `cancel-in-progress: false` — intentionally different from `ci.yml`. A queued cron run must never cancel another scheduled run.
- `if: failure() && github.event_name == 'schedule'` — the event-name guard means `workflow_dispatch` failures (e.g., during testing) do NOT open issues. Both conditions matter.
- `permissions: issues: write` is scoped to the `report-failure` job only. The `checks` job inherits the workflow default (read-only).
- `actions/checkout@v4` is needed in `report-failure` because the helper script lives in the repo.
- `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` — `gh` CLI reads `GH_TOKEN` automatically. `GITHUB_TOKEN` is auto-provisioned by Actions; no manual secret setup required.

- [ ] **Step 2: Validate YAML syntax locally**

```bash
actionlint .github/workflows/scheduled.yml 2>/dev/null \
  || python -c "import yaml; yaml.safe_load(open('.github/workflows/scheduled.yml')); print('ok')"
```

Expected: `actionlint` prints nothing, or the python fallback prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scheduled.yml
git commit -m "Add weekly scheduled dependency-check workflow

Runs the reusable _checks.yml every Monday at 06:00 UTC.
On scheduled-event failure only, opens or updates a rolling
GitHub issue via .github/scripts/report-scheduled-failure.sh.
Manual workflow_dispatch failures intentionally do not report.

Closes the implementation portion of
planning/specs/2026-06-08-scheduled-dep-check-design.md."
```

---

### Task 4: Live validation on the branch (green path + red path)

**Goal:** Prove the scheduled workflow actually works on GitHub. This task makes temporary edits, observes behavior, and reverts the temporary edits before merge. The final commit on the branch must be Task 3's commit.

**Files (during this task, all changes will be reverted before merge):**
- Temporarily modify: `.github/workflows/_checks.yml` (inject failure)
- Temporarily modify: `.github/workflows/scheduled.yml` (drop event guard)

- [ ] **Step 1: Push the branch if not already pushed**

```bash
git push -u origin "$(git branch --show-current)"
```

- [ ] **Step 2: Green-path test via workflow_dispatch**

In the browser: GitHub → Actions tab → `scheduled-dep-check` workflow → "Run workflow" button → select your branch → Run.

Wait for the run to complete. Expected:
- `checks` job: all five matrix entries + lint pass (same as `ci.yml`).
- `report-failure` job: **skipped** (the `if:` condition is false because the run succeeded AND the event is `workflow_dispatch` not `schedule`).

If `report-failure` runs unexpectedly, the `if:` condition is wrong — re-read Task 3 Step 1.

- [ ] **Step 3: Red-path test — inject a failure**

Edit `.github/workflows/_checks.yml`. Change the lint job's last step from:

```yaml
      - run: just install lint-ci
```

to:

```yaml
      - run: just install lint-ci && false
```

Edit `.github/workflows/scheduled.yml`. Change the `report-failure` job's `if:` from:

```yaml
    if: failure() && github.event_name == 'schedule'
```

to:

```yaml
    if: failure()
```

These temporary edits force a failure and remove the event guard so a `workflow_dispatch` failure does report.

- [ ] **Step 4: Push the temp edits**

```bash
git add .github/workflows/_checks.yml .github/workflows/scheduled.yml
git commit -m "TEMP: force failure for scheduled-workflow validation"
git push
```

- [ ] **Step 5: Trigger workflow_dispatch and observe**

Re-run the `scheduled-dep-check` workflow via the Actions tab button.

Expected:
- `checks` job: lint fails (matrix pytest jobs still pass; that's fine — `report-failure` only needs the overall `checks` to fail, which it will).
- `report-failure` job: runs and succeeds.
- A new issue appears in the Issues tab, titled **"Scheduled dependency check failed"**, with label `scheduled-failure`, body referencing the failing run URL.

- [ ] **Step 6: Trigger workflow_dispatch a second time and verify comment behavior**

Re-run again from the Actions tab.

Expected:
- Same outcome — but **no second issue is created**. Instead, the existing issue gets a comment: `Failed again: <run-url>`.

If a second issue is created instead of a comment, the `gh issue list` filter in the script is wrong. Re-read Task 2 Step 1.

- [ ] **Step 7: Close the test issue manually**

In the browser, close the test issue (and optionally delete it — your call). This proves the "first failure after close opens a new issue" branch works on the next cron run, though we won't dispatch a third time here.

- [ ] **Step 8: Revert the temp commit**

```bash
git revert HEAD --no-edit
git push
```

This produces a "Revert TEMP: ..." commit. Confirm the workflow files now match Task 1 and Task 3 contents exactly:

```bash
grep -F "just install lint-ci && false" .github/workflows/_checks.yml \
  && echo "STILL BROKEN" \
  || echo "ok: _checks.yml reverted"
grep -F "github.event_name == 'schedule'" .github/workflows/scheduled.yml \
  && echo "ok: scheduled.yml reverted" \
  || echo "STILL MISSING GUARD"
```

Expected: both lines print `ok: ...`.

- [ ] **Step 9: Tidy the branch history (optional)**

If you'd rather not have `TEMP: ...` + `Revert TEMP: ...` commits in the merged history, interactively squash them out before opening the PR:

```bash
# Only on a topic branch, never on main.
git rebase -i origin/main
# In the editor: drop the TEMP commit and its Revert.
git push --force-with-lease
```

If you'd rather preserve the audit trail (TEMP + Revert), skip this step. Both are reasonable.

---

### Task 5: Open the PR

**Goal:** Hand off to review and merge.

- [ ] **Step 1: Confirm the branch is clean and main-CI-green**

```bash
git status                        # working tree clean
git log --oneline origin/main..HEAD   # review the commits you're shipping
```

Expected commits (in this order, possibly with TEMP + Revert pair if not squashed):
1. Extract CI lint and pytest jobs into reusable workflow
2. Add helper script to file rolling issue on scheduled CI failure
3. Add weekly scheduled dependency-check workflow

The latest GitHub Actions run for `main` workflow on this branch should be green.

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Weekly scheduled dependency-breakage check" --body "$(cat <<'EOF'
## Summary
- Extracts the existing lint + pytest matrix from `ci.yml` into a reusable workflow `_checks.yml` (`workflow_call`).
- `ci.yml` becomes a thin caller; push/PR behavior is unchanged.
- New `scheduled.yml` runs `_checks.yml` every Monday at 06:00 UTC (also dispatchable). On scheduled failure, opens or updates a single rolling tracking issue labeled `scheduled-failure` via `gh issue` in `.github/scripts/report-scheduled-failure.sh`.
- Manual workflow_dispatch failures intentionally do not open issues.

Implements `planning/specs/2026-06-08-scheduled-dep-check-design.md`.

## Test plan
- [x] Refactored `ci.yml` runs green on this PR (same matrix as before).
- [x] `scheduled-dep-check` workflow dispatched on the branch passes green; `report-failure` is skipped on success.
- [x] Forced failure on the branch (temp commit, since reverted) produced a tracking issue with the correct title, label, and run URL.
- [x] A second forced failure produced a comment on the same issue, not a second issue.
EOF
)"
```

Returns the PR URL on success.

---

## Self-Review

Verified against `planning/specs/2026-06-08-scheduled-dep-check-design.md`:

1. **Spec coverage check:**
   - Cadence: weekly Monday 06:00 UTC → Task 3 Step 1, cron `"0 6 * * 1"`. ✓
   - Scope mirror of ci.yml (lint + 3.10–3.14 matrix) → Task 1 Step 2, identical jobs. ✓
   - Reusable workflow refactor → Tasks 1 and 3. ✓
   - Single rolling issue with `scheduled-failure` label → Task 2 Step 1, script + Task 4 red-path validation. ✓
   - `workflow_dispatch` failures do not report → Task 3 Step 1 `if:` guard + Task 4 Step 2 verifies skip on dispatch success path. ✓
   - `gh` CLI, no third-party action → Task 2 script. ✓
   - `permissions: issues: write` scoped to report job → Task 3 Step 1. ✓
   - `cancel-in-progress: false` on scheduled → Task 3 Step 1. ✓
   - Helper script at `.github/scripts/report-scheduled-failure.sh` → Task 2. ✓
   - Pre-merge testing via dispatch (green) and forced failure (red) → Task 4 Steps 2 and 3–7. ✓

2. **Placeholder scan:** No TBD / TODO / "add appropriate error handling" / "similar to Task N" found. All code blocks contain literal file contents or literal commands. ✓

3. **Type/name consistency:** Label name `scheduled-failure` consistent across Task 2 script and Task 4 expectations. Workflow name `scheduled-dep-check` consistent between Task 3 and Task 4 instructions. File paths consistent everywhere. ✓
