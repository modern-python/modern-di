---
date: 2026-06-25
slug: canonical-convention-repo
spec: design.md
---

# canonical-convention-repo — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the portable planning convention into a personal canonical repo
(`lesnik512/planning-convention`) that agents apply/update into any repo via an
`APPLY.md` instruction doc + a `planning/.convention-version` marker, and mark
`modern-di` as consumer #1.

**Architecture:** Assemble the canonical repo's contents in a scratch git repo
(verbatim copies of `index.py` + `_templates/` from this repo, plus four authored
docs: `README.md`, `convention.md`, `APPLY.md`, `CHANGELOG.md`), create+push the
GitHub repo tagged `1.0.0`, then wire `modern-di` as the first consumer (a
`.convention-version` marker + a README pointer + a `deferred.md` update).

**Tech Stack:** Markdown; Python 3.10+ stdlib (`index.py`, unchanged); `git`;
`gh`; `just`/`uv` (consumer side).

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/canonical-convention-repo` (already created, in `modern-di`).

**Commit strategy:** Per-task commits in `modern-di`. The canonical repo is a
separate git repo assembled in a scratch dir and pushed in Task 2.

## Global Constraints

- **Canonical repo is `lesnik512/planning-convention`** — personal, public. All
  URLs/pointers use exactly this `owner/name`.
- **Seed version is `1.0.0`** (a git tag on the canonical repo); the `modern-di`
  marker `planning/.convention-version` contains exactly `1.0.0`.
- **`index.py` and `_templates/*` are copied VERBATIM** from `modern-di` into the
  canonical repo — do not modify convention behavior (out of scope).
- **Generalize org-specific wording** only in `convention.md` (drop
  "modern-python repos"); never alter lane rules, frontmatter, or validator logic.
- **Scratch dir for the canonical repo:**
  `/private/tmp/claude-501/-Users-kevinsmith-src-pypi-modern-di/2084d40e-c07a-4b49-8c7e-d906534227ed/scratchpad/planning-convention`
  (call it `$CANON` below).
- `modern-di` gates stay green: `just check-planning`, `just lint-ci`,
  `just docs-build`.

---

### Task 1: Assemble the canonical repo contents (scratch git repo)

**Files (all under `$CANON`):**
- Create: `index.py` (verbatim copy), `_templates/{change,design,plan,decision,release}.md` (verbatim copies)
- Create: `README.md`, `convention.md`, `APPLY.md`, `CHANGELOG.md`, `.github/workflows/check.yml`

- [ ] **Step 1: Initialize the scratch repo and copy the clean files verbatim**

  ```bash
  CANON=/private/tmp/claude-501/-Users-kevinsmith-src-pypi-modern-di/2084d40e-c07a-4b49-8c7e-d906534227ed/scratchpad/planning-convention
  rm -rf "$CANON" && mkdir -p "$CANON/_templates" "$CANON/.github/workflows"
  git -C "$CANON" init -q
  REPO=/Users/kevinsmith/src/pypi/modern-di
  cp "$REPO/planning/index.py" "$CANON/index.py"
  cp "$REPO"/planning/_templates/{change,design,plan,decision,release}.md "$CANON/_templates/"
  ```

  Verify: `ls "$CANON" "$CANON/_templates"` shows `index.py` and the five templates.

- [ ] **Step 2: Write `$CANON/convention.md`** — the portable prose, generalized.

  It is the current `modern-di` `planning/README.md` **Quick path + Conventions**
  block (its lines 7–107) with two changes: a generic top intro instead of the
  modern-di intro, and the org-specific adoption blockquote replaced. Concretely,
  the file is:

  ````markdown
  # Planning convention

  The portable two-axis planning convention: `architecture/` (repo root) holds the
  living truth about what the system does **now**; `planning/changes/` records how
  it got there. This file is the canonical convention prose — adopt or update it in
  a repo via [`APPLY.md`](APPLY.md).

  ## Quick path (start here)

  > The fast lane for making a change. The full reference is in
  > [Conventions](#conventions) below — read it only when this isn't enough.

  **1. Choose a lane — first matching rule wins:**

  1. Any of: needs design judgment · new file/module · public-API change ·
     cross-cutting or multi-file · non-trivial test design → **Full**
     (`design.md` + `plan.md`)
  2. Purely mechanical: typo · dep bump · linter/formatter/CI tweak ·
     mechanical rename · single-line config → **Tiny** (no bundle, conventional
     commit)
  3. Small-but-real, none of the above: ≲30 LOC net · ≤2 files · no new file ·
     no public-API change · one straightforward test → **Lightweight**
     (`change.md`)

  Ambiguous between two? Take the heavier. A `change.md` that outgrows its lane
  splits into `design.md` + `plan.md`.

  **2. Create the bundle** (Full / Lightweight only):
  `planning/changes/YYYY-MM-DD.NN-<slug>/`, where `.NN` is a zero-padded
  intra-day counter. Copy the matching template from
  [`_templates/`](_templates/).

  **3. Ship in the implementing PR:** hand-edit the affected
  `architecture/<capability>.md`, fill `outcome:` in
  the bundle frontmatter, and run `just check-planning` before pushing.

  ## Conventions

  > This is the portable convention. It is consumed by other repos from the
  > canonical source repo; see [`APPLY.md`](APPLY.md) to adopt or update it. A
  > consuming repo's change index (`just index`) and its "Other" pointers are
  > added per repo, not part of this portable core.

  ### Two axes, never mixed

  - **`architecture/` (repo root) — the present.** One file per capability,
    living prose, updated in the same PR that ships the change. The truth home.
  - **`planning/changes/` — the past-and-pending.** One folder per change,
    kept in place after ship.

  A change **promotes** its conclusions into the affected
  `architecture/<capability>.md` by hand **in the implementing PR, alongside the
  code** — the edit rides in the same diff and is reviewed with it, never applied
  as a separate post-merge step. That hand-edit is what keeps `architecture/`
  true; the bundle stays in `changes/` as the *why*.

  ### Change bundles

  A change is a folder `changes/YYYY-MM-DD.NN-<slug>/`:

  - `YYYY-MM-DD` — proposal date; `.NN` — zero-padded intra-day counter
    (`.01`, `.02`, …) that breaks same-date ties so the timeline sorts stably.
  - `<slug>` — kebab-case description, not a story ID.

  `summary` is written when the change is created (it is the change's
  one-liner). The implementing PR fills `outcome`
  **in the branch**, alongside the code and the `architecture/`
  promotion — no post-merge bookkeeping, no folder move.

  ### Three lanes

  | Lane | Artifacts | Use when |
  |------|-----------|----------|
  | **Full** | `design.md` + `plan.md` | design judgment; new file/module; public-API change; cross-cutting/multi-file; non-trivial test design |
  | **Lightweight** | `change.md` | small-but-real: ≲30 LOC net, ≤2 files, no new file, no public-API change, single straightforward test |
  | **Tiny** | none — conventional commit | typo, dep bump, linter/formatter/CI tweak, mechanical rename, single-line config |

  Heavier lane wins on ambiguity. A `change.md` that outgrows its lane splits
  into `design.md` + `plan.md`.

  ### Artifacts at a glance

  - **`design.md`** — the spec: the *thinking* (why, design, trade-offs, scope).
  - **`plan.md`** — the plan: the *sequencing* (the executor's task checklist).
  - **`change.md`** — both, condensed, for the lightweight lane.
  - **`releases/<semver>.md`** — per-release user-facing notes.
  - **`audits/<date>-<slug>.md`** — findings from a code/docs/bug-hunt sweep;
    spawns fix changes.
  - **`retros/<date>-<slug>.md`** — what we learned after a body of work.
  - **`deferred.md`** — real-but-unscheduled items, each with a revisit trigger.
  - **`decisions/<YYYY-MM-DD>-<slug>.md`** — one file per design decision taken
    (especially options *rejected*), each with a revisit trigger; listed by
    `just index`.

  Templates live in [`_templates/`](_templates/).

  ### Frontmatter

  `design.md` / `change.md`: `date`, `slug`, `summary` (single line), `outcome`.
  `plan.md`: `date`, `slug`, `spec`. `decisions/*.md`: `status`
  (accepted|superseded), `date`, `slug`, `summary`, `supersedes`, `superseded_by`.
  Files in `architecture/` carry **no** frontmatter — living prose, dated by git.

  **`outcome`** is filled at ship time: one line, ~1–3 sentences (≤ ~300 chars),
  stating the realized result — what shipped and its effect (deviations from the
  plan included), written so a future reader grasps the consequence without
  opening the diff. It is distinct from `summary`, which is the pre-ship intent
  one-liner.
  ````

  (This is `modern-di`'s portable block verbatim except the new `# Planning
  convention` intro and the generalized `## Conventions` blockquote — both shown
  above. Do NOT include the repo-local `## Index` / `## Other` sections.)

- [ ] **Step 3: Write `$CANON/APPLY.md`** — the agent apply/update engine:

  ````markdown
  # APPLY.md — adopt or update this planning convention in a repo

  You are an agent applying this canonical planning convention to a **target
  repo** (the repo you are working in). The canonical repo is
  `lesnik512/planning-convention`. Work on a feature branch in the target repo and
  open a PR at the end.

  ## 0. Read the target's baseline

  Read `planning/.convention-version` in the target repo.
  - **Missing** → FRESH ADOPT: do every section below, including §5.
  - **Present** (e.g. `1.0.0`) → UPDATE: read this repo's `CHANGELOG.md` and apply
    only entries with a version GREATER than the recorded one; skip §5.

  ## 1. Overwrite the clean files verbatim

  Owned by the canonical repo — copy exactly, replacing any local version (local
  edits to them are intentionally discarded):

  - `index.py` → target `planning/index.py`
  - `_templates/*` → target `planning/_templates/*`

  ## 2. Merge the convention prose

  `convention.md` here is the portable Quick-path + Conventions prose. In the
  target's `planning/README.md`, replace the existing block (from the `## Quick
  path` heading through the end of the `## Conventions`/Frontmatter section) with
  `convention.md`'s body **below its `# Planning convention` title** (the target
  keeps its own page title/intro). Keep the target's repo-local sections (its
  `## Index`, `## Other`). Ensure the target README still points at
  `planning/.convention-version` and this canonical repo.

  ## 3. Judgment-merge the mixed files

  Edit in place, don't overwrite:

  - **`justfile`**: ensure these recipes exist and match —
    ```
    index:
        uv run python planning/index.py
    check-planning:
        uv run python planning/index.py --check
    ```
    and ensure `lint-ci` runs `uv run python planning/index.py --check` as a step.
    (If the repo uses another task runner, adapt and note the deviation in the PR.)
  - **`CLAUDE.md`**: ensure (a) a `## Workflow` pointer to the Quick path in
    `planning/README.md` as the authoritative convention, and (b) the
    `## Architecture` orientation carries the promotion reminder: "When a change
    alters a capability's behavior, update the matching
    `architecture/<capability>.md` in the same PR." Preserve all other
    repo-specific content.

  ## 4. Apply CHANGELOG deltas (UPDATE only)

  For each CHANGELOG entry newer than the recorded version, make the change it
  describes if §§1–3 did not already cover it (most land via the §1 verbatim copy).

  ## 5. Fresh-adopt scaffolding (FRESH ADOPT only)

  Create if absent: `planning/{changes,decisions,releases}/`, `planning/deferred.md`
  (one-line header), and `architecture/README.md` stating the promotion rule (one
  file per capability; shipping a change hand-edits the matching file in the same
  PR). The repo authors its own capability files.

  ## 6. Record, verify, open a PR

  - Write the applied version (the latest CHANGELOG version) to
    `planning/.convention-version`.
  - `just check-planning` → must print `planning: OK`.
  - `just lint-ci` → must pass.
  - Commit and open a PR whose body lists the applied CHANGELOG deltas (or "fresh
    adopt at vX.Y.Z"), so the human reviews exactly what changed.
  ````

- [ ] **Step 4: Write `$CANON/CHANGELOG.md`**:

  ````markdown
  # Changelog

  Versions are git tags. A consuming repo records the version it last applied in
  `planning/.convention-version`; on update, apply every entry newer than that.

  ## 1.0.0 — 2026-06-25

  Initial extraction of the convention into this canonical repo. Baseline:

  - **Validator + index** (`index.py`): `--check` validates bundle shape, required
    frontmatter, field validity, `outcome` presence on specs, and `plan.md`
    `spec:` link resolution; default mode prints the change index as a flat
    newest-first list. Wired into `just lint-ci` in consumers.
  - **Lean frontmatter**: change specs are `date`/`slug`/`summary`/`outcome`;
    plans are `date`/`slug`/`spec`; decisions keep `status` (accepted|superseded)
    + `supersedes`/`superseded_by`. No `pr` or `status` on change bundles.
  - **Quick-path on-ramp** with a first-match lane decision; full Conventions
    reference; `_templates/` for change/design/plan/decision/release.
  - **architecture/ promotion**: a behavior change updates the matching
    `architecture/<capability>.md` in the same PR; consumers carry an agent-facing
    reminder in `CLAUDE.md`'s `## Architecture` note.
  ````

- [ ] **Step 5: Write `$CANON/README.md`**:

  ````markdown
  # planning-convention

  Canonical source for a portable, agent-friendly planning convention: a two-axis
  model (`architecture/` truth home + `planning/changes/` bundles), a
  `check-planning` validator, lean frontmatter, and a Quick-path on-ramp.

  ## What's here

  - [`convention.md`](convention.md) — the portable convention prose (Quick path +
    Conventions).
  - [`index.py`](index.py) — the validator + index generator.
  - [`_templates/`](_templates/) — change · design · plan · decision · release.
  - [`APPLY.md`](APPLY.md) — how an agent applies/updates this into a repo.
  - [`CHANGELOG.md`](CHANGELOG.md) — versioned deltas (git tags are the versions).

  ## Adopt or update it in a repo

  Point an agent (e.g. Claude Code) at [`APPLY.md`](APPLY.md) from the target repo:
  it copies the script + templates, merges the convention prose and the
  `justfile`/`CLAUDE.md` snippets, records the applied version in
  `planning/.convention-version`, verifies with `just check-planning`, and opens a
  PR. Updating re-runs the same flow, applying only the CHANGELOG entries newer
  than the recorded version.
  ````

- [ ] **Step 6: Write `$CANON/.github/workflows/check.yml`** — a minimal smoke
  test that `index.py` runs (it needs a fixture, since the canonical repo has no
  `changes/` dir):

  ````yaml
  name: check
  on: [push, pull_request]
  jobs:
    smoke:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - name: index.py --check passes on a fixture
          run: |
            mkdir -p changes/2026-01-01.01-fixture
            printf -- '---\ndate: 2026-01-01\nslug: fixture\nsummary: x\noutcome: x\n---\n# x\n' \
              > changes/2026-01-01.01-fixture/change.md
            python index.py --check
            rm -rf changes
        - name: templates parse as frontmatter
          run: |
            python - <<'PY'
            import pathlib, sys
            sys.path.insert(0, ".")
            from index import parse_frontmatter
            for p in pathlib.Path("_templates").glob("*.md"):
                assert parse_frontmatter(p.read_text()), p
            print("templates OK")
            PY
  ````

- [ ] **Step 7: Verify locally and commit the scratch repo**

  ```bash
  cd "$CANON"
  # Smoke: index.py runs against a fixture
  mkdir -p changes/2026-01-01.01-fixture
  printf -- '---\ndate: 2026-01-01\nslug: fixture\nsummary: x\noutcome: x\n---\n# x\n' > changes/2026-01-01.01-fixture/change.md
  python index.py --check    # expect: planning: OK
  rm -rf changes
  # Templates parse
  python -c "import sys; sys.path.insert(0,'.'); from index import parse_frontmatter; import pathlib; [print(p.name, bool(parse_frontmatter(p.read_text()))) for p in pathlib.Path('_templates').glob('*.md')]"
  git add -A && git commit -q -m "Initial canonical planning-convention (1.0.0)"
  ```
  Expected: `planning: OK`; every template prints `True`.

---

### Task 2: Create and push the GitHub repo, tag 1.0.0

**Files:** none in `modern-di` (operates on `$CANON` + GitHub).

- [ ] **Step 1: Confirm gh can act as `lesnik512`**

  ```bash
  gh auth status
  ```
  Expected: an account that can create `lesnik512/planning-convention`. If the
  authenticated account is NOT `lesnik512` (or lacks permission), STOP and report
  DONE_WITH_CONCERNS — the maintainer creates+pushes the repo manually using the
  `$CANON` contents (steps below), then resume Task 3.

- [ ] **Step 2: Create, push, and tag**

  ```bash
  cd "$CANON"
  git branch -M main
  gh repo create lesnik512/planning-convention --public --source=. --remote=origin --push
  git tag 1.0.0
  git push origin 1.0.0
  ```
  Expected: repo exists at `https://github.com/lesnik512/planning-convention` with
  `main` + tag `1.0.0`; the `check` workflow runs green.

- [ ] **Step 3: Confirm**

  ```bash
  gh repo view lesnik512/planning-convention --json url,defaultBranchRef -q '.url'
  gh api repos/lesnik512/planning-convention/tags -q '.[].name'
  ```
  Expected: the URL prints and `1.0.0` is listed.

---

### Task 3: Wire `modern-di` as consumer #1 and finish

**Files:**
- Create: `planning/.convention-version`
- Modify: `planning/README.md` (the `## Conventions` blockquote), `planning/deferred.md`

- [ ] **Step 1: Add the version marker**

  ```bash
  printf '1.0.0\n' > /Users/kevinsmith/src/pypi/modern-di/planning/.convention-version
  ```

- [ ] **Step 2: Repoint the `## Conventions` blockquote** in
  `planning/README.md`. Replace the current blockquote (the four lines starting
  "> This section is the portable convention — identical across the") with:

  ```markdown
  > This is the portable convention, sourced from the canonical repo
  > [`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
  > (applied version in [`.convention-version`](.convention-version)). To update
  > it, run that repo's `APPLY.md` flow. The generated change index (`just index`)
  > and the `## Other` pointers below are repo-local.
  ```

- [ ] **Step 3: Update the `deferred.md` sibling-rollout entry.** Replace the body
  of the existing "Roll the agent-friendly planning updates into sibling repos"
  section with a version that references the new mechanism:

  ```markdown
  ## Roll the planning convention into sibling repos — from 2026-06-25

  The convention now lives in the canonical repo
  [`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
  (v1.0.0); `modern-di` is consumer #1 (`planning/.convention-version`). Sibling
  repos (`faststream-outbox`, the modern-di integrations) still carry an older,
  hand-copied form.

  **Revisit trigger:** next time a sibling repo's planning convention is touched,
  or in a dedicated sync pass — from each sibling, run the canonical repo's
  `APPLY.md` flow (fresh adopt: it has no `.convention-version` yet), verify with
  `just check-planning`, and open a PR.
  ```

- [ ] **Step 4: Verify `modern-di` is green**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  just check-planning   # planning: OK
  just lint-ci          # all pass
  just docs-build       # OK
  ```

- [ ] **Step 5: Fill this bundle's `outcome` and commit**

  In `planning/changes/2026-06-25.03-canonical-convention-repo/design.md`, replace
  the placeholder `outcome:` with the realized one-liner (e.g. "Extracted the
  convention into `lesnik512/planning-convention` (v1.0.0) with an `APPLY.md`
  agent-apply flow + `.convention-version` marker; `modern-di` wired as consumer
  #1."). Then:

  ```bash
  git add planning/.convention-version planning/README.md planning/deferred.md \
    planning/changes/2026-06-25.03-canonical-convention-repo/design.md
  git commit -m "feat(planning): adopt canonical convention repo as consumer #1

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  git push -u origin feat/canonical-convention-repo
  gh pr create --fill
  ```
  Run `just check-planning` once more before pushing (the bundle now has a real
  `outcome`). Watch PR CI to green.

---

## Self-Review

**Spec coverage:**
- Design §1 (canonical repo layout) → Task 1 (all six files + verbatim copies). ✓
- Design §2 (version marker) → Task 3 Step 1. ✓
- Design §3 (`APPLY.md` procedure) → Task 1 Step 3 (full content). ✓
- Design §4 (generalized prose) → Task 1 Step 2 (intro + blockquote generalized). ✓
- Design §5 (`modern-di` as consumer #1) → Task 3 Steps 1–2. ✓
- Design §6 / Operations (create + push repo) → Task 2. ✓
- Out-of-scope sibling rollout → Task 3 Step 3 (`deferred.md`). ✓
- Testing (fixture `--check`, templates parse, modern-di gates, idempotent dry-run)
  → Task 1 Step 7 + the `check.yml` workflow + Task 3 Step 4. ✓

**Placeholder scan:** None. The only deferred value is this bundle's own
`outcome`, filled in Task 3 Step 5 at ship time (per the convention). All authored
files carry complete content.

**Type/consistency:** `1.0.0` is used identically across the tag, the marker, the
CHANGELOG, the README pointer, and the deferred entry. `$CANON` path is defined
once and reused. The `index.py`/`parse_frontmatter` referenced in `check.yml` and
Task 1 Step 7 match the real module (unchanged from `modern-di`).
