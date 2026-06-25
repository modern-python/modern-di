---
status: draft
date: 2026-06-25
slug: agent-friendly-planning-convention
spec: design.md
pr: null
---

# agent-friendly-planning-convention — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the portable planning convention agent-friendly — add a
`just check-planning` validator, bring all existing bundles to green, and
restructure the convention text into a Quick-path on-ramp + de-duplicated
pointer.

**Architecture:** Extend `planning/index.py` with a `--check` mode (reusing its
`parse_frontmatter`) exposed as `just check-planning` and wired into
`just lint-ci`. Add a Quick-path section atop `planning/README.md` (the agent
on-ramp, with a deterministic first-match lane decision) and shrink the
duplicated CLAUDE.md `## Workflow` prose to a pointer. Backfill frontmatter on
15 historical bundles and standardize `plan.md`'s `spec:` to a bundle-relative
path.

**Tech Stack:** Python 3.10+ stdlib only (`pathlib`, `re`, `sys`); `just`; `uv`.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/agent-friendly-planning-convention` (already created).

**Commit strategy:** Per-task commits.

## Global Constraints

- **Line length: 120 chars.** `ruff` runs with `select = ["ALL"]`; `ty` for
  types. `just lint` must pass clean.
- **Do NOT add a committed test that imports `planning/index.py`.** It is
  currently never imported, so the 100% coverage gate (`--cov=.`) does not
  measure it. Importing it from `tests/` would pull `render`/`load_*`/`main`
  into the coverage set and break the gate. The validator is verified via the
  **CLI only** (`just check-planning`) against throwaway fixtures and the real
  repo. Throwaway fixtures are removed before committing — never committed.
- **`spec:` is a bundle-relative path** (Fork 1 ruling): always resolvable from
  the bundle directory (e.g. `design.md`, `../../../audits/x.md`).
- **`status: shipped` ⇒ `pr` and `outcome` both non-null**, enforced for **all**
  bundles, historical included (Fork 2 ruling). No grandfathering.
- This change does **not** promote to `architecture/` — it is process/tooling,
  like the original `portable-planning-convention` adoption. Its "promotion" is
  the README + CLAUDE.md edits it already makes.
- `just check-planning` must report **all** violations in one run (not
  fail-fast).

---

### Task 1: Add the `--check` validator and `just check-planning` recipe

**Files:**
- Modify: `planning/index.py` (add `import re`, validation constants/functions,
  `--check` branch in `main`)
- Modify: `justfile` (add `check-planning` recipe)

**Interfaces:**
- Produces: `check() -> list[str]` (returns violation strings; reused by `main`);
  CLI `python planning/index.py --check` (exit 1 + itemized stderr on
  violations, exit 0 + `planning: OK` otherwise). `just check-planning` wraps it.
- Consumes: existing `parse_frontmatter`, `CHANGES_DIR`, `DECISIONS_DIR`.

- [ ] **Step 1: Add `import re` to the imports block**

  In `planning/index.py`, the current imports are:

  ```python
  import pathlib
  import sys
  ```

  Change to:

  ```python
  import pathlib
  import re
  import sys
  ```

- [ ] **Step 2: Add validation constants** after the existing `GROUPS = (...)`
  tuple:

  ```python
  VALID_STATUS = {"draft", "approved", "shipped", "superseded"}
  VALID_DECISION_STATUS = {"accepted", "superseded"}
  DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
  BUNDLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d{2}-(?P<slug>.+)$")
  ALLOWED_BUNDLE_FILES = {"design.md", "plan.md", "change.md"}
  SPEC_REQUIRED = ("status", "date", "slug", "summary")
  PLAN_REQUIRED = ("status", "date", "slug", "spec")
  DECISION_REQUIRED = ("status", "date", "slug", "summary")
  ```

- [ ] **Step 3: Add the validation functions** just above `def main()`:

  ```python
  def _require(fields: dict[str, str], keys: tuple[str, ...], rel: str, violations: list[str]) -> None:
      """Append a violation for each required key that is absent or empty."""
      for key in keys:
          if not fields.get(key):
              violations.append(f"{rel}: missing or empty frontmatter key '{key}'")


  def _check_common(
      fields: dict[str, str], allowed_status: set[str], dir_slug: str | None, rel: str, violations: list[str]
  ) -> None:
      """Validate status/date/slug fields shared by every artifact type."""
      status = fields.get("status", "")
      if status and status not in allowed_status:
          violations.append(f"{rel}: invalid status '{status}' (allowed: {', '.join(sorted(allowed_status))})")
      date = fields.get("date", "")
      if date and not DATE_RE.match(date):
          violations.append(f"{rel}: date '{date}' is not YYYY-MM-DD")
      slug = fields.get("slug", "")
      if dir_slug and slug and slug != dir_slug:
          violations.append(f"{rel}: slug '{slug}' does not match directory slug '{dir_slug}'")


  def _check_spec_file(path: pathlib.Path, rel: str, dir_slug: str | None, violations: list[str]) -> None:
      """Validate a design.md / change.md spec file."""
      fields = parse_frontmatter(path.read_text(encoding="utf-8"))
      _require(fields, SPEC_REQUIRED, rel, violations)
      _check_common(fields, VALID_STATUS, dir_slug, rel, violations)
      if fields.get("status") == "shipped":
          for key in ("pr", "outcome"):
              if not fields.get(key):
                  violations.append(f"{rel}: status is 'shipped' but '{key}' is empty")


  def _check_plan_file(
      path: pathlib.Path, bundle: pathlib.Path, rel: str, dir_slug: str | None, violations: list[str]
  ) -> None:
      """Validate a plan.md file, including that its spec: link resolves."""
      fields = parse_frontmatter(path.read_text(encoding="utf-8"))
      _require(fields, PLAN_REQUIRED, rel, violations)
      _check_common(fields, VALID_STATUS, dir_slug, rel, violations)
      spec = fields.get("spec", "")
      if spec and not (bundle / spec).resolve().exists():
          violations.append(f"{rel}: spec link '{spec}' does not resolve to a file")


  def _check_bundle(bundle: pathlib.Path, violations: list[str]) -> None:
      """Validate one change bundle directory."""
      rel = f"changes/{bundle.name}"
      match = BUNDLE_RE.match(bundle.name)
      dir_slug = match.group("slug") if match else None
      if match is None:
          violations.append(f"{rel}: directory name is not 'YYYY-MM-DD.NN-slug'")
      for child in sorted(bundle.iterdir()):
          if child.name not in ALLOWED_BUNDLE_FILES:
              violations.append(
                  f"{rel}/{child.name}: unexpected file in bundle (allowed: {', '.join(sorted(ALLOWED_BUNDLE_FILES))})"
              )
      design = bundle / "design.md"
      change = bundle / "change.md"
      plan = bundle / "plan.md"
      if not design.exists() and not change.exists():
          violations.append(f"{rel}: bundle has neither design.md nor change.md")
      for spec_file in (design, change):
          if spec_file.exists():
              _check_spec_file(spec_file, f"{rel}/{spec_file.name}", dir_slug, violations)
      if plan.exists():
          _check_plan_file(plan, bundle, f"{rel}/plan.md", dir_slug, violations)


  def _check_decision(path: pathlib.Path, violations: list[str]) -> None:
      """Validate one decision file."""
      rel = f"decisions/{path.name}"
      fields = parse_frontmatter(path.read_text(encoding="utf-8"))
      _require(fields, DECISION_REQUIRED, rel, violations)
      _check_common(fields, VALID_DECISION_STATUS, None, rel, violations)


  def check() -> list[str]:
      """Validate every bundle and decision; return the list of violation strings."""
      violations: list[str] = []
      for bundle in sorted(CHANGES_DIR.iterdir()):
          if bundle.is_dir():
              _check_bundle(bundle, violations)
      if DECISIONS_DIR.is_dir():
          for path in sorted(DECISIONS_DIR.glob("*.md")):
              if path.name == "README.md" or path.name.startswith("_"):
                  continue
              _check_decision(path, violations)
      return violations
  ```

- [ ] **Step 4: Add the `--check` branch to `main`**

  Current:

  ```python
  def main() -> int:
      """Print the listing to stdout."""
      sys.stdout.write(render(load_bundles(), load_decisions()))
      return 0
  ```

  Replace with:

  ```python
  def main() -> int:
      """Print the listing to stdout, or validate bundles with --check."""
      if "--check" in sys.argv[1:]:
          violations = check()
          if violations:
              sys.stderr.write(f"planning: {len(violations)} violation(s)\n")
              for violation in violations:
                  sys.stderr.write(f"  - {violation}\n")
              return 1
          sys.stdout.write("planning: OK\n")
          return 0
      sys.stdout.write(render(load_bundles(), load_decisions()))
      return 0
  ```

- [ ] **Step 5: Add the `check-planning` recipe to `justfile`**

  After the existing `index:` recipe (the last recipe in the file), add:

  ```just
  # Validate planning bundles + decisions (frontmatter, lanes, spec links); CI runs this.
  check-planning:
      uv run python planning/index.py --check
  ```

- [ ] **Step 6: Verify the index still renders unchanged**

  Run: `just index`
  Expected: the same Markdown listing as before (changes by status, then
  decisions). The `--check` addition must not alter default stdout.

- [ ] **Step 7: Prove detection with a throwaway fixture (NOT committed)**

  Create a deliberately-broken throwaway bundle:

  ```bash
  mkdir -p planning/changes/2099-01-01.99-zzz-throwaway-fixture
  printf -- '---\nstatus: bogus\ndate: not-a-date\nslug: wrong-slug\n---\n# x\n' \
    > planning/changes/2099-01-01.99-zzz-throwaway-fixture/design.md
  ```

  Run: `just check-planning`
  Expected: exit 1; output includes lines for the fixture —
  `invalid status 'bogus'`, `date 'not-a-date' is not YYYY-MM-DD`,
  `slug 'wrong-slug' does not match directory slug 'zzz-throwaway-fixture'`, and
  `missing or empty frontmatter key 'summary'`.

  Then remove it:

  ```bash
  rm -rf planning/changes/2099-01-01.99-zzz-throwaway-fixture
  ```

- [ ] **Step 8: Confirm the validator runs against the real repo**

  Run: `just check-planning`
  Expected: exit 1 with ~24 violations in historical bundles (these are fixed in
  Task 2). This confirms the validator works end-to-end. Do **not** wire it into
  `lint-ci` yet — that happens after Task 2 turns the repo green.

- [ ] **Step 9: Lint and commit**

  Run: `just lint` — must pass clean (address any ruff/ty findings inline).
  Then:

  ```bash
  git add planning/index.py justfile
  git commit -m "feat(planning): add just check-planning bundle validator

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 2: Bring all historical bundles to green, then wire into lint-ci

**Files:**
- Modify (backfill `pr`): the 8 `design.md` listed below.
- Modify (backfill `outcome`): the 7 `change.md` listed below.
- Modify (`spec:` → path): 6 `plan.md` + `planning/_templates/plan.md`.
- Modify: `justfile` (`lint-ci` recipe).

**Interfaces:**
- Consumes: `just check-planning` from Task 1 as the gate.
- Produces: a repo where `just check-planning` exits 0.

- [ ] **Step 1: Backfill `pr:` on the 8 shipped `design.md` bundles**

  Set the `pr:` frontmatter field (currently `null`) in each, using this mapping
  (derived from `planning/releases/*.md` + merge commits):

  | bundle `design.md` | `pr:` |
  |---|---|
  | `2026-06-05.01-bug-hunt-audit` | `188-197` |
  | `2026-06-05.02-singleton-rlock` | `188` |
  | `2026-06-05.03-validate-rework` | `189` |
  | `2026-06-07.01-mkdocs-github-pages-migration` | `198` |
  | `2026-06-08.01-scheduled-dep-check` | `200` |
  | `2026-06-09.01-docs-improvements` | `198` |
  | `2026-06-09.02-migration-guide-from-that-depends` | `198` |
  | `2026-06-12.01-code-docs-audit` | `202-203` |

  **Uncertain ones — verify first:** `docs-improvements` and
  `migration-guide-from-that-depends` have no dedicated merged PR (their docs
  shipped with the GitHub-Pages migration). Confirm with
  `gh pr list --state merged --search "<slug>"` or
  `git log --oneline --all -- <doc path>`; if a dedicated PR exists, use it,
  otherwise keep `198` (the docs-migration PR they rode in with). Note the
  choice in the commit message.

  Edit example (`bug-hunt-audit`): change `pr: null` → `pr: "188-197"` (quote
  range values so the index renders `#188-197`).

- [ ] **Step 2: Backfill `outcome:` on the 7 shipped `change.md` bundles**

  Each already has `pr:`; only `outcome:` is missing. Write a one-line
  `outcome:` for each, condensed from that bundle's own `summary:` / body (the
  result is already described in-file — do not invent new facts):

  - `2026-06-12.02-audit-fixes`
  - `2026-06-13.01-audit-fixes-round2`
  - `2026-06-13.02-alias-scope-transparency`
  - `2026-06-14.03-audit-doc-rulings-batch1`
  - `2026-06-14.04-audit-fixes-batch2`
  - `2026-06-14.05-audit-fixes-batch3`
  - `2026-06-14.06-audit-fixes-batch4-5`

  Worked example (`audit-fixes-batch4-5`, whose summary already states the
  result) — add under the `pr: 220` line:

  ```yaml
  outcome: Closed every actionable 2026-06-14 audit finding (P-6/R-3/X-2 test hardening; X-3/X-4/X-5 DX/docs); only won't-fix R-4/R-5/R-6 and the A-1 nogil follow-up remain.
  ```

- [ ] **Step 3: Standardize `plan.md` `spec:` to a bundle-relative path**

  Set `spec: design.md` in each of these `plan.md` files (each has a sibling
  `design.md`, so it resolves):

  - `2026-06-13.01-docs-ux-audit/plan.md` — currently missing `spec:`
  - `2026-06-14.02-set-context-cross-scope-staleness/plan.md` — bare slug
  - `2026-06-23.01-wiring-plan-extraction/plan.md` — bare slug
  - `2026-06-23.02-inline-error-messages/plan.md` — bare slug
  - `2026-06-23.03-suggester/plan.md` — bare slug

  For `2026-06-13.02-docs-ux-fixes/plan.md` (missing `status`/`date`/`slug`/
  `spec`), set the full frontmatter, mirroring its sibling `design.md`'s
  `status`/`pr` and keeping the existing body:

  ```yaml
  ---
  status: shipped
  date: 2026-06-13
  slug: docs-ux-fixes
  spec: design.md
  pr: <copy from sibling design.md>
  ---
  ```

  (Read `2026-06-13.02-docs-ux-fixes/design.md` to copy its exact `status` and
  `pr`.)

- [ ] **Step 4: Fix the template so new plans inherit the path convention**

  In `planning/_templates/plan.md` frontmatter, change `spec: my-change` to
  `spec: design.md`.

- [ ] **Step 5: Run the gate to green**

  Run: `just check-planning`
  Expected: exit 0, `planning: OK`. If any violation remains, fix it and re-run
  (the validator lists all violations each run).

- [ ] **Step 6: Wire `check-planning` into `lint-ci`**

  Current `lint-ci` recipe:

  ```just
  lint-ci:
      uv run eof-fixer . --check
      uv run ruff format --check
      uv run ruff check --no-fix
      uv run ty check
  ```

  Add the check as a final line:

  ```just
  lint-ci:
      uv run eof-fixer . --check
      uv run ruff format --check
      uv run ruff check --no-fix
      uv run ty check
      uv run python planning/index.py --check
  ```

- [ ] **Step 7: Verify lint-ci is green and commit**

  Run: `just lint-ci`
  Expected: all checks pass, including `planning: OK`.

  ```bash
  git add planning/changes planning/_templates/plan.md justfile
  git commit -m "fix(planning): backfill historical bundle frontmatter; gate in lint-ci

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Add the Quick-path on-ramp to planning/README.md

**Files:**
- Modify: `planning/README.md` (insert a new section between the intro
  paragraph and `## Conventions`)

- [ ] **Step 1: Insert the Quick-path section**

  In `planning/README.md`, immediately after the intro paragraph (the line
  ending "...records *how it got there*.") and before `## Conventions`, insert:

  ```markdown
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
  `architecture/<capability>.md`, set `status: shipped` + `pr:` + `outcome:` in
  the bundle frontmatter, and run `just check-planning` before pushing.
  ```

- [ ] **Step 2: Verify the gate still passes (README is not a bundle, but confirm nothing regressed)**

  Run: `just check-planning`
  Expected: exit 0, `planning: OK`.

- [ ] **Step 3: Verify the docs build is unaffected**

  Run: `just docs-build`
  Expected: build succeeds. (`docs_dir: docs` excludes `planning/`, so this only
  confirms no collateral breakage.)

- [ ] **Step 4: Commit**

  ```bash
  git add planning/README.md
  git commit -m "docs(planning): add Quick-path on-ramp with first-match lane decision

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: De-duplicate CLAUDE.md `## Workflow` down to a pointer

**Files:**
- Modify: `CLAUDE.md` (`## Workflow` section, currently the intro + 6 bullets)

- [ ] **Step 1: Replace the duplicated Workflow prose with a pointer**

  In `CLAUDE.md`, replace the entire `## Workflow` body — from the
  "Planning follows a portable two-axis convention..." intro through the
  `- **Templates live in...**` and `- **Shipping a change**...` bullets, but
  **keeping** the `- **Cutting a release (maintainers)**...` bullet verbatim —
  with:

  ```markdown
  ## Workflow

  Planning uses a portable two-axis convention — `architecture/` (repo root) is
  the living **truth home** and promotion target; `planning/changes/` holds the
  per-change bundles. **Start at the
  [Quick path](planning/README.md#quick-path-start-here)** in
  `planning/README.md` to choose a lane, create a bundle, and ship — that file
  is the authoritative spec. Run `just check-planning` to validate bundles and
  `just index` to print the change listing. The `## Architecture` section above
  is quick orientation; `architecture/` holds the authoritative account.

  - **Cutting a release (maintainers)** is tag-driven via
    [`.github/workflows/release.yml`](.github/workflows/release.yml): write the
    notes at `planning/releases/<version>.md` (used verbatim as the GitHub Release
    body), then push a bare semver tag off green `main` —
    `git tag 2.19.2 && git push origin 2.19.2`. The workflow runs `just publish`
    (the tag sets the version via `uv version`; no `pyproject.toml` bump) to PyPI,
    then creates the GitHub Release — PyPI first, so a failed publish creates no
    Release. Pre-releases use the PEP 440 form (`2.0.0rc1`, not `2.0.0-alpha.5`).
    PyPI is irreversible; there is no CI gate (a tag is the commitment point).
  ```

- [ ] **Step 2: Confirm no unique content was lost**

  Read the removed bullets against `planning/README.md` "Conventions". Confirm
  every removed fact (architecture/ truth home, bundle layout, decisions lane,
  templates, shipping/promotion) is present there. The only repo-specific bullet
  — release-cutting — is retained above. If anything removed is NOT in the
  README, restore it to CLAUDE.md.

- [ ] **Step 3: Commit**

  ```bash
  git add CLAUDE.md
  git commit -m "docs: de-duplicate CLAUDE.md Workflow to a pointer at the Quick path

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 5: Record the sibling-repo rollout and finish the branch

**Files:**
- Modify: `planning/deferred.md` (append the rollout follow-up)
- Modify: `planning/changes/2026-06-25.01-agent-friendly-planning-convention/design.md`
  and `plan.md` (ship frontmatter, once the PR number is known)

- [ ] **Step 1: Append the sibling-rollout follow-up to `deferred.md`**

  Add at the end of `planning/deferred.md`:

  ```markdown
  ## Roll the agent-friendly planning updates into sibling repos — from 2026-06-25

  The Quick-path on-ramp (`planning/README.md`) and the `index.py --check`
  validator (`just check-planning`, wired into `just lint-ci`) shipped here in
  [2026-06-25.01-agent-friendly-planning-convention](changes/2026-06-25.01-agent-friendly-planning-convention/design.md).
  They are written to be copied verbatim. Sibling modern-python repos (e.g.
  `faststream-outbox`) still carry the older prose-table convention and the
  `spec: <slug>` plan template.

  **Revisit trigger:** next time a sibling repo's planning convention is touched,
  or in a dedicated sync pass — copy the Quick-path section and the `--check`
  additions, switch that repo's `_templates/plan.md` to `spec: design.md`, and
  wire `check-planning` into its `just lint-ci`.
  ```

- [ ] **Step 2: Full verification**

  Run: `just lint-ci` — all checks pass including `planning: OK`.
  Run: `just test-ci` — full suite green, 100% coverage (unchanged; no test
  imports `index.py`).
  Run: `just docs-build` — succeeds.

- [ ] **Step 3: Commit the follow-up**

  ```bash
  git add planning/deferred.md
  git commit -m "docs(planning): defer sibling-repo rollout of the agent-friendly updates

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

- [ ] **Step 4: Push and open the PR**

  ```bash
  git push -u origin feat/agent-friendly-planning-convention
  gh pr create --fill
  ```

- [ ] **Step 5: Ship this bundle's frontmatter (in-branch, after the PR number is known)**

  Per the convention, set this bundle's lifecycle fields in the implementing PR.
  In both `design.md` and `plan.md` frontmatter set `status: shipped` and
  `pr: <this PR number>`; in `design.md` also fill `outcome:` with a one-line
  result. Then:

  ```bash
  git add planning/changes/2026-06-25.01-agent-friendly-planning-convention
  git commit -m "docs(planning): mark agent-friendly-planning-convention shipped

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  git push
  ```

  Run `just check-planning` once more before this push — with `status: shipped`
  the bundle now requires `pr` + `outcome`, so the gate confirms they are set.
  This change does **not** edit `architecture/` (process/tooling; see Global
  Constraints). Watch PR CI to green.

---

## Self-Review

**Spec coverage:**
- Design §1 (three tiers: Quick path / Conventions / templates) → Task 3
  (Quick-path tier 1), Task 4 (de-dup → pointer); Conventions + `_templates/`
  left intact per design. ✓
- Design §1 lane decision procedure (finding 4) → Task 3 Step 1. ✓
- Design §2 (`--check` validator + recipe + lint-ci wiring) → Task 1 + Task 2
  Step 6. ✓ All five invariant classes (bundle shape, frontmatter completeness,
  field validity, lifecycle completeness, link integrity) are in Task 1 Step 3. ✓
- Design §3 (bootstrapping existing bundles to green) → Task 2 Steps 1–5. ✓
- Operations (sibling rollout follow-up) → Task 5 Step 1. ✓
- Fork 1 ruling (spec = path; fix template) → Task 2 Steps 3–4. ✓
- Fork 2 ruling (backfill all 15) → Task 2 Steps 1–2. ✓

**Placeholder scan:** No "TBD"/"handle edge cases". The only deliberately
deferred values are the two genuinely-PR-less docs bundles (Task 2 Step 1),
which name the exact command to resolve them and a documented fallback — not a
placeholder. The `outcome:` backfills name their source (each bundle's own
summary) with a worked example.

**Type consistency:** `check()`, `parse_frontmatter`, `_check_*` signatures match
between Task 1 Step 3 (definitions) and Step 4 (`main` calls `check()`). The
`--check` CLI contract used in Task 1 Steps 7–8 and Task 2 Step 5 matches the
`main` implementation. `spec: design.md` is used consistently across Task 2
Steps 3–4 and the validator's resolution check.
