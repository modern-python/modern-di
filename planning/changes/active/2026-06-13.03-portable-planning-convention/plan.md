---
status: draft
date: 2026-06-13
slug: portable-planning-convention
spec: design.md
pr: null
---

# Portable planning convention — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `planning/specs/` + `planning/plans/` layout with the
faststream-outbox two-axis convention — an `architecture/` truth home plus
`planning/changes/{active,archive}/` bundles — and back-author the
`architecture/` capability prose.

**Architecture:** Pure docs/repo-structure change; no Python source is touched.
Migration uses `git mv` to preserve history. `architecture/` and `planning/`
both sit outside `docs_dir: docs`, so the published mkdocs site is unaffected;
the docs build is run only as a no-collateral-breakage check. Frozen historical
bundles keep their internal prose untouched — only live inbound links in
`planning/releases/` are repointed.

**Tech Stack:** Markdown, `git mv`, `just` (`lint-ci`), `mkdocs`, `ripgrep`.

**Branch:** `chore/portable-planning-convention` (already created; the spec is
committed there).

**Commit strategy:** Per-task commits.

**Canonical source to copy from:**
`/Users/kevinsmith/src/pypi/faststream-outbox/planning/README.md` (Conventions
section) and `/Users/kevinsmith/src/pypi/faststream-outbox/planning/_templates/`.

---

### Task 1: Scaffold directories and copy templates

**Files:**
- Create: `planning/_templates/design.md`, `plan.md`, `change.md` (copied)
- Create dirs: `planning/changes/active/`, `planning/changes/archive/`, `architecture/`

Empty dirs aren't tracked by git; no `.gitkeep` is needed because Task 2 fills
`archive/` and the active bundle already populates `active/`.

- [ ] **Step 0: Scope the `plan.md` gitignore rule to root (PREREQUISITE)**

  `.gitignore:22` has a bare `plan.md` that ignores **every** `plan.md` in the
  repo — which would silently drop every bundle plan. Scope it to root-only:

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  # change the line `plan.md` to `/plan.md`
  git check-ignore planning/_templates/plan.md   # expect: no output after the fix
  ```
  (May already be applied on the branch — verify with the `git check-ignore`
  above returning nothing before proceeding.)

- [ ] **Step 1: Create the directory skeleton**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  mkdir -p planning/changes/active planning/changes/archive planning/_templates architecture
  ```

- [ ] **Step 2: Copy the three templates byte-for-byte**

  ```bash
  cp /Users/kevinsmith/src/pypi/faststream-outbox/planning/_templates/design.md planning/_templates/design.md
  cp /Users/kevinsmith/src/pypi/faststream-outbox/planning/_templates/plan.md   planning/_templates/plan.md
  cp /Users/kevinsmith/src/pypi/faststream-outbox/planning/_templates/change.md planning/_templates/change.md
  ```

- [ ] **Step 3: Verify the templates copied**

  Run: `ls planning/_templates/`
  Expected: `change.md  design.md  plan.md`

- [ ] **Step 4: Commit**

  ```bash
  git add planning/_templates/
  git commit -m "chore: add planning _templates (design/plan/change)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

  (The empty `changes/` dirs are committed in Task 3 once they hold files; no
  `.gitkeep` is committed.)

---

### Task 2: Migrate the 17 spec/plan files into 11 archive bundles

Each `git mv` both relocates and renames to `design.md` / `plan.md`. Do **not**
edit file contents in this task — only move. Frontmatter is normalized in Task 3.

**Files (move map):**

| From | To |
|------|----|
| `planning/specs/2026-06-05-bug-hunt-audit-design.md` | `planning/changes/archive/2026-06-05.01-bug-hunt-audit/design.md` |
| `planning/plans/2026-06-05-bug-hunt-audit-plan.md` | `planning/changes/archive/2026-06-05.01-bug-hunt-audit/plan.md` |
| `planning/specs/2026-06-05-singleton-rlock-design.md` | `planning/changes/archive/2026-06-05.02-singleton-rlock/design.md` |
| `planning/plans/2026-06-05-singleton-rlock-plan.md` | `planning/changes/archive/2026-06-05.02-singleton-rlock/plan.md` |
| `planning/specs/2026-06-05-validate-rework-design.md` | `planning/changes/archive/2026-06-05.03-validate-rework/design.md` |
| `planning/plans/2026-06-05-validate-rework-plan.md` | `planning/changes/archive/2026-06-05.03-validate-rework/plan.md` |
| `planning/specs/2026-06-07-mkdocs-github-pages-migration-design.md` | `planning/changes/archive/2026-06-07.01-mkdocs-github-pages-migration/design.md` |
| `planning/plans/2026-06-07-mkdocs-github-pages-migration.md` | `planning/changes/archive/2026-06-07.01-mkdocs-github-pages-migration/plan.md` |
| `planning/specs/2026-06-08-scheduled-dep-check-design.md` | `planning/changes/archive/2026-06-08.01-scheduled-dep-check/design.md` |
| `planning/plans/2026-06-08-scheduled-dep-check-plan.md` | `planning/changes/archive/2026-06-08.01-scheduled-dep-check/plan.md` |
| `planning/specs/2026-06-09-docs-improvements-design.md` | `planning/changes/archive/2026-06-09.01-docs-improvements/design.md` |
| `planning/specs/2026-06-09-migration-guide-from-that-depends.md` | `planning/changes/archive/2026-06-09.02-migration-guide-from-that-depends/design.md` |
| `planning/specs/2026-06-12-code-docs-audit-design.md` | `planning/changes/archive/2026-06-12.01-code-docs-audit/design.md` |
| `planning/plans/2026-06-12-code-docs-audit.md` | `planning/changes/archive/2026-06-12.01-code-docs-audit/plan.md` |
| `planning/plans/2026-06-12-audit-fixes.md` | `planning/changes/archive/2026-06-12.02-audit-fixes/plan.md` |
| `planning/plans/2026-06-13-audit-fixes-round2.md` | `planning/changes/archive/2026-06-13.01-audit-fixes-round2/plan.md` |
| `planning/plans/2026-06-13-alias-scope-transparency.md` | `planning/changes/archive/2026-06-13.02-alias-scope-transparency/plan.md` |

- [ ] **Step 1: Create the 11 bundle directories**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  cd planning/changes/archive
  mkdir -p 2026-06-05.01-bug-hunt-audit 2026-06-05.02-singleton-rlock 2026-06-05.03-validate-rework \
           2026-06-07.01-mkdocs-github-pages-migration 2026-06-08.01-scheduled-dep-check \
           2026-06-09.01-docs-improvements 2026-06-09.02-migration-guide-from-that-depends \
           2026-06-12.01-code-docs-audit 2026-06-12.02-audit-fixes \
           2026-06-13.01-audit-fixes-round2 2026-06-13.02-alias-scope-transparency
  cd /Users/kevinsmith/src/pypi/modern-di
  ```

- [ ] **Step 2: `git mv` each file per the move map above**

  Run each move (17 total), e.g.:

  ```bash
  git mv planning/specs/2026-06-05-bug-hunt-audit-design.md planning/changes/archive/2026-06-05.01-bug-hunt-audit/design.md
  git mv planning/plans/2026-06-05-bug-hunt-audit-plan.md   planning/changes/archive/2026-06-05.01-bug-hunt-audit/plan.md
  ```

  …continuing for all 17 rows.

- [ ] **Step 3: Confirm the old dirs are empty and remove them**

  ```bash
  ls planning/specs planning/plans   # expect: empty
  rmdir planning/specs planning/plans
  ```

- [ ] **Step 4: Verify the bundle tree**

  Run: `find planning/changes/archive -type f | sort`
  Expected: 17 files — every bundle has `design.md` and/or `plan.md` matching the
  move map (paired bundles have both; `docs-improvements` and `migration-guide`
  have only `design.md`; `audit-fixes`, `audit-fixes-round2`,
  `alias-scope-transparency` have only `plan.md`).

- [ ] **Step 5: Commit**

  ```bash
  git add -A planning/
  git commit -m "chore: migrate specs/plans into changes/archive bundles

  17 files relocated via git mv into 11 dated bundles; specs/ and plans/ removed.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Normalize frontmatter on the migrated bundles

Set the top YAML frontmatter of each migrated file to match the convention. If a
file already has a frontmatter block (delimited by the first pair of `---`),
replace its keys to match; if it has none, prepend one. **Only touch the
frontmatter block — leave the body untouched.**

`design.md` frontmatter shape:
```yaml
---
status: shipped
date: <date>
slug: <slug>
supersedes: null
superseded_by: null
pr: <pr>
outcome: <one line>
---
```
`plan.md` frontmatter shape:
```yaml
---
status: shipped
date: <date>
slug: <slug>
spec: <spec>
pr: <pr>
---
```

**Per-bundle values** (`date` and `slug` come from the bundle id; `spec` in
`plan.md` is `design.md` for paired bundles, or the audit-report path for
plan-only bundles):

| Bundle | pr | outcome (design.md) | plan.md `spec` |
|--------|----|--------------------|----------------|
| `2026-06-05.01-bug-hunt-audit` | `null` | `Four-dimension bug-hunt audit harness; report in audits/2026-06-05-bug-hunt-audit-report.md; 18 findings actioned in 2.15.0 (#188–#197).` | `design.md` |
| `2026-06-05.02-singleton-rlock` | `null` | `RLock guards singleton creation; shipped in 2.15.0.` | `design.md` |
| `2026-06-05.03-validate-rework` | `null` | `validate() reworked for transitive cycle/scope checks; shipped in 2.15.0.` | `design.md` |
| `2026-06-07.01-mkdocs-github-pages-migration` | `null` | `Docs hosting moved to GitHub Pages at modern-di.modern-python.org.` | `design.md` |
| `2026-06-08.01-scheduled-dep-check` | `null` | `Weekly scheduled dependency-check workflow (.github/workflows/scheduled.yml).` | `design.md` |
| `2026-06-09.01-docs-improvements` | `null` | `Docs-site improvements shipped.` | _(design-only — no plan.md)_ |
| `2026-06-09.02-migration-guide-from-that-depends` | `null` | `docs/migration/from-that-depends.md published.` | _(design-only — no plan.md)_ |
| `2026-06-12.01-code-docs-audit` | `null` | `Full code+docs audit harness; produced the 57-finding report in audits/2026-06-12-code-docs-audit-report.md.` | `design.md` |
| `2026-06-12.02-audit-fixes` | `#202` | _(plan-only — no design.md)_ | `../../../audits/2026-06-12-code-docs-audit-report.md` |
| `2026-06-13.01-audit-fixes-round2` | `#203` | _(plan-only — no design.md)_ | `../../../audits/2026-06-12-code-docs-audit-report.md` |
| `2026-06-13.02-alias-scope-transparency` | `#207` | _(plan-only — no design.md)_ | `../../../audits/2026-06-12-code-docs-audit-report.md` |

- [ ] **Step 1: Set frontmatter on each `design.md`**

  For each of the 8 `design.md` files, edit the frontmatter to the design shape
  with `status: shipped`, the bundle's `date`/`slug`, `pr` and `outcome` from
  the table. Leave `supersedes`/`superseded_by` as `null`.

- [ ] **Step 2: Set frontmatter on each `plan.md`**

  For each of the 9 `plan.md` files, edit the frontmatter to the plan shape with
  `status: shipped`, the bundle's `date`/`slug`, `spec` and `pr` from the table.

- [ ] **Step 3: Verify every migrated file starts with `status: shipped`**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  for f in $(find planning/changes/archive -name '*.md'); do
    head -2 "$f" | grep -q '^status: shipped' || echo "MISSING frontmatter: $f"
  done
  ```
  Expected: no output.

- [ ] **Step 4: Commit**

  ```bash
  git add planning/changes/archive/
  git commit -m "chore: normalize frontmatter on archived change bundles

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: Create `planning/README.md`

Copy the faststream-outbox README, then adapt only the preamble (repo name) and
replace everything from `## Index` onward with the modern-di Index. The
Conventions section stays byte-identical and is verified by diff.

**Files:**
- Create: `planning/README.md`

- [ ] **Step 1: Copy the source README**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  cp /Users/kevinsmith/src/pypi/faststream-outbox/planning/README.md planning/README.md
  ```

- [ ] **Step 2: Replace the preamble (first 5 lines) with the modern-di version**

  Replace the title + intro paragraph (everything before `## Conventions`) with:

  ```markdown
  # Planning

  Specs, plans, and change history for `modern-di`. The living truth about *what
  the system does now* lives in [`architecture/`](../architecture/) at the repo
  root; this directory records *how it got there*.
  ```

- [ ] **Step 3: Replace everything from `## Index` to end of file with the modern-di Index**

  ```markdown
  ## Index

  ### Active

  - **[portable-planning-convention](changes/active/2026-06-13.03-portable-planning-convention/design.md)**
    (2026-06-13) — Adopt the two-axis convention: `architecture/` truth +
    `changes/` bundles + portable README, copied from faststream-outbox.

  ### Archived (shipped)

  - **[alias-scope-transparency](changes/archive/2026-06-13.02-alias-scope-transparency/plan.md)**
    (#207, 2026-06-13) — Deprecate decorative `Alias(scope=...)`; `validate()`
    checks scope transitively via `effective_scope` (X-4). Plan-only; spec = the
    code-docs audit report.
  - **[audit-fixes-round2](changes/archive/2026-06-13.01-audit-fixes-round2/plan.md)**
    (#203, 2026-06-13) — Round-2 fixes for the 21 deferred code+docs audit
    findings. Plan-only; spec = the audit report.
  - **[audit-fixes](changes/archive/2026-06-12.02-audit-fixes/plan.md)**
    (#202, 2026-06-12) — First batch of code+docs audit fixes. Plan-only; spec =
    the audit report.
  - **[code-docs-audit](changes/archive/2026-06-12.01-code-docs-audit/design.md)**
    (2026-06-12) — Full code+docs audit harness; produced the 57-finding report.
  - **[migration-guide-from-that-depends](changes/archive/2026-06-09.02-migration-guide-from-that-depends/design.md)**
    (2026-06-09) — Migration guide from `that-depends`. Design-only.
  - **[docs-improvements](changes/archive/2026-06-09.01-docs-improvements/design.md)**
    (2026-06-09) — Docs-site improvements. Design-only.
  - **[scheduled-dep-check](changes/archive/2026-06-08.01-scheduled-dep-check/design.md)**
    (2026-06-08) — Weekly scheduled dependency-check workflow.
  - **[mkdocs-github-pages-migration](changes/archive/2026-06-07.01-mkdocs-github-pages-migration/design.md)**
    (2026-06-07) — Docs hosting moved to GitHub Pages.
  - **[validate-rework](changes/archive/2026-06-05.03-validate-rework/design.md)**
    (2.15.0, 2026-06-05) — Reworked `validate()` for transitive cycle/scope
    checks.
  - **[singleton-rlock](changes/archive/2026-06-05.02-singleton-rlock/design.md)**
    (2.15.0, 2026-06-05) — RLock-guarded singleton creation.
  - **[bug-hunt-audit](changes/archive/2026-06-05.01-bug-hunt-audit/design.md)**
    (2.15.0, 2026-06-05) — Four-dimension bug-hunt audit harness + report.

  ## Other

  - **[`architecture/`](../architecture/)** at the repo root — the living
    capability truth (scopes, containers, providers, resolution, validation,
    testing & overrides). This is the promotion target on every ship.
  - **[audits/](audits/)** — findings reports (2026-06-05 bug-hunt, 2026-06-12
    code+docs).
  - **[deferred.md](deferred.md)** — real-but-unscheduled items with revisit
    triggers.
  - **[scripts/bug-hunt-audit.workflow.mjs](scripts/bug-hunt-audit.workflow.mjs)**
    — repo-specific extra (the reusable audit harness), not part of the portable
    core.
  ```

- [ ] **Step 4: Verify the Conventions section is byte-identical to the source**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  diff <(sed -n '/^## Conventions/,/^## Index/p' planning/README.md) \
       <(sed -n '/^## Conventions/,/^## Index/p' /Users/kevinsmith/src/pypi/faststream-outbox/planning/README.md)
  ```
  Expected: no output (identical through the `## Index` line).

- [ ] **Step 5: Commit**

  ```bash
  git add planning/README.md
  git commit -m "docs: planning README — portable Conventions + modern-di Index

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 5: Confirm the active bundle is in place

The active bundle already exists
(`2026-06-13.03-portable-planning-convention/` with `design.md` + `plan.md`,
committed on the branch).

- [ ] **Step 1: Verify active holds exactly this change**

  Run: `ls planning/changes/active/`
  Expected: `2026-06-13.03-portable-planning-convention`

  No commit needed — this is a confirmation checkpoint only.

---

### Task 6: Back-author `architecture/README.md`

**Files:**
- Create: `architecture/README.md`

This is the index for the truth home. No frontmatter (living prose).

- [ ] **Step 1: Write `architecture/README.md`**

  Content (full file):

  ```markdown
  # Architecture

  The living truth about what `modern-di` does **now** — one file per capability,
  updated by hand whenever a change ships. The *why* and *how it got here* live in
  [`../planning/changes/`](../planning/changes/); this directory is the present.

  These files carry **no frontmatter** — they are prose, dated by git.

  ## Capabilities

  - [scopes.md](scopes.md) — the `Scope` hierarchy and the resolution rule.
  - [containers.md](containers.md) — the `Container`, its registries, child
    containers, and lifecycle.
  - [providers.md](providers.md) — `Group`, `Factory`/caching, `ContextProvider`,
    `Alias`.
  - [resolution.md](resolution.md) — how `resolve()` wires dependencies from type
    hints.
  - [validation.md](validation.md) — `validate()` cycle and scope checks.
  - [testing-and-overrides.md](testing-and-overrides.md) — overrides and the
    `modern-di-pytest` integration.

  ## Promotion rule

  Shipping a change hand-edits the affected capability file(s) here to match the
  new reality, then archives the change bundle under
  [`../planning/changes/archive/`](../planning/changes/archive/).
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add architecture/README.md
  git commit -m "docs(architecture): add truth-home index

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

> **Tasks 7–12 author one `architecture/<capability>.md` each.** They are
> independent and ideal for parallel subagents. For every file: **no
> frontmatter**; living prose; verify each claim against the cited source files
> before writing it (source from the code and shipped docs, not memory); 120-char
> line wrap; end with a single trailing newline. After writing, run
> `uv run ruff format --check .` is **not** applicable to markdown — instead the
> repo's eof-fixer runs in `just lint`; a final `just lint-ci` in Task 14 covers
> formatting. Each task commits its one file.

### Task 7: Author `architecture/scopes.md`

**Files:**
- Create: `architecture/scopes.md`
- Read first: `modern_di/scope.py`, `modern_di/container.py` (`find_container`),
  `docs/introduction/`, `CLAUDE.md` (Scope hierarchy).

- [ ] **Step 1: Write the file** covering, as present-tense prose:
  - `Scope` is an `IntEnum` with `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`.
  - The resolution rule: a provider bound to scope S resolves only from a
    container at scope S or deeper (higher int); resolving a deeper-scoped
    provider from a shallower container raises a clear error (name the error and
    quote its shape from `modern_di/errors.py`).
  - How `find_container(scope)` walks the parent chain to locate the container at
    the right scope.
  - A short worked example (APP service vs REQUEST service).

- [ ] **Step 2: Verify claims** — re-open `scope.py` and confirm the enum values
  and `find_container` behavior match the prose. Fix any drift.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/scopes.md
  git commit -m "docs(architecture): scopes capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 8: Author `architecture/containers.md`

**Files:**
- Create: `architecture/containers.md`
- Read first: `modern_di/container.py`, `modern_di/providers/container_provider.py`,
  the registry classes (`providers_registry`, `cache_registry`,
  `context_registry`, `overrides_registry`), `docs/` container pages, `CLAUDE.md`
  (Container tree, Registries).

- [ ] **Step 1: Write the file** covering:
  - `Container` is the entry point; root via `Container(scope=Scope.APP, groups=[...])`.
  - `build_child_container(scope=..., context={...})` creates children that share
    the parent's `providers_registry` and `overrides_registry` but get their own
    `cache_registry` and `context_registry`.
  - The four-registry table (which are shared vs per-container) and why.
  - Close/reopen lifecycle (finalizers run on close; reopen semantics) — confirm
    exact behavior from `container.py`.
  - `container_provider` resolves to the `Container` itself.

- [ ] **Step 2: Verify claims** against `container.py` and the registry sources.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/containers.md
  git commit -m "docs(architecture): containers capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 9: Author `architecture/providers.md`

**Files:**
- Create: `architecture/providers.md`
- Read first: `modern_di/group.py`, `modern_di/providers/factory.py`,
  `modern_di/providers/context_provider.py`, the `Alias` provider source,
  `modern_di/providers/__init__.py`, `docs/providers/`, `CLAUDE.md` (Group and
  Provider declaration).

- [ ] **Step 1: Write the file** covering:
  - `Group` is a non-instantiable namespace; providers are class-level attributes.
  - `Factory(scope=..., creator=...)` parses the creator's `__init__` hints at
    declaration time; recursive type-based resolution.
  - Singleton = `Factory(cache_settings=CacheSettings())`; there is no separate
    `Singleton` class. Sync and async finalizers via `CacheSettings`.
  - `kwargs={}` supplies static args that bypass type resolution;
    `skip_creator_parsing=True` for un-introspectable callables.
  - `ContextProvider` for runtime-injected values; `Alias` and its **deprecated**
    decorative `scope=` parameter (removal in 3.0).

- [ ] **Step 2: Verify claims** against `factory.py` and the provider sources —
  especially the deprecation wording and `CacheSettings` fields.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/providers.md
  git commit -m "docs(architecture): providers capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 10: Author `architecture/resolution.md`

**Files:**
- Create: `architecture/resolution.md`
- Read first: `modern_di/container.py` (`resolve`, `resolve_provider`),
  `modern_di/types_parser.py`, `docs/` resolution/recipes pages, `CLAUDE.md`
  (Resolution flow).

- [ ] **Step 1: Write the file** covering the numbered flow:
  1. `resolve(SomeType)` → lookup in `providers_registry` → `resolve_provider`.
  2. `resolve_provider` checks `overrides_registry` first (override short-circuit).
  3. `find_container(scope)` locates the right-scope container.
  4. `cache_registry` hit returns immediately.
  5. kwargs compiled by matching each parsed parameter type to a provider,
     resolved recursively; `kwargs=` precedence over type resolution.
  6. creator called; result cached if `cache_settings` set.
  - `X | None` parameters with no provider are injected as `None` (nullable
    wiring); confirm exact behavior from the code.

- [ ] **Step 2: Verify claims** against `container.py` and `types_parser.py`.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/resolution.md
  git commit -m "docs(architecture): resolution capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 11: Author `architecture/validation.md`

**Files:**
- Create: `architecture/validation.md`
- Read first: the `validate()` implementation in `modern_di/container.py`, the
  `effective_scope` logic, `errors.py`, the
  `changes/archive/2026-06-05.03-validate-rework/` and
  `changes/archive/2026-06-13.02-alias-scope-transparency/` bundles, `CLAUDE.md`.

- [ ] **Step 1: Write the file** covering:
  - `validate=True` at container creation, or `container.validate()` explicitly;
    zero cost when disabled.
  - Cycle detection over the provider graph.
  - Transitive scope check through aliases via `effective_scope` (X-4).
  - The decorative `Alias(scope=...)` is exempt from the scope-order check and is
    deprecated (removal in 3.0).

- [ ] **Step 2: Verify claims** against the `validate()` source and the X-4 bundle.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/validation.md
  git commit -m "docs(architecture): validation capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 12: Author `architecture/testing-and-overrides.md`

**Files:**
- Create: `architecture/testing-and-overrides.md`
- Read first: the override methods in `modern_di/container.py`
  (`override`/`reset_override`), the `OverridesRegistry` source, `CLAUDE.md`
  (Testing patterns), and the `modern-di-pytest` description in `CLAUDE.md`.

- [ ] **Step 1: Write the file** covering:
  - `container.override(provider, mock)` / `reset_override(provider)`; backed by
    the shared `OverridesRegistry`; override short-circuits resolution (link to
    `resolution.md`).
  - Test patterns: `Group` subclass with providers as attributes; resolve by
    reference (`resolve_provider`) or by type (`resolve`); scope-chain tests via
    `build_child_container`.
  - The sibling `modern-di-pytest` package: `modern_di_fixture(type_or_provider)`
    and `expose(*groups)` (duplicate attr names raise `ValueError`); note that
    `modern-di` itself does not depend on it.

- [ ] **Step 2: Verify claims** against the override source and `CLAUDE.md`.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/testing-and-overrides.md
  git commit -m "docs(architecture): testing & overrides capability

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 13: Repoint inbound links in `planning/releases/`

Only the `specs/`/`plans/` directory links break; `audits/`, `scripts/`, and
`deferred.md` links stay valid. Frozen bundle-internal references are **not**
touched.

**Files:**
- Modify: `planning/releases/2.15.0.md` (lines 72–73)
- Modify: `planning/releases/2.16.0.md` (line 64)
- Modify: `planning/releases/2.17.0.md` (line 25)

- [ ] **Step 1: Edit `2.15.0.md`** — replace the two lines:

  ```markdown
  - Specs: [`planning/specs/`](../specs/) — audit design, singleton RLock, validate rework
  - Plans: [`planning/plans/`](../plans/) — implementation plans for each major fix
  ```
  with:
  ```markdown
  - Change bundles: [`bug-hunt-audit`](../changes/archive/2026-06-05.01-bug-hunt-audit/design.md), [`singleton-rlock`](../changes/archive/2026-06-05.02-singleton-rlock/design.md), [`validate-rework`](../changes/archive/2026-06-05.03-validate-rework/design.md) — design + plan in each.
  ```

- [ ] **Step 2: Edit `2.16.0.md`** — replace line 64:

  ```markdown
  - Plans: [`planning/plans/2026-06-12-code-docs-audit.md`](../plans/2026-06-12-code-docs-audit.md), [`2026-06-12-audit-fixes.md`](../plans/2026-06-12-audit-fixes.md), [`2026-06-13-audit-fixes-round2.md`](../plans/2026-06-13-audit-fixes-round2.md)
  ```
  with:
  ```markdown
  - Plans: [`code-docs-audit`](../changes/archive/2026-06-12.01-code-docs-audit/plan.md), [`audit-fixes`](../changes/archive/2026-06-12.02-audit-fixes/plan.md), [`audit-fixes-round2`](../changes/archive/2026-06-13.01-audit-fixes-round2/plan.md)
  ```

- [ ] **Step 3: Edit `2.17.0.md`** — replace line 25:

  ```markdown
  - Plan: [`planning/plans/2026-06-13-alias-scope-transparency.md`](../plans/2026-06-13-alias-scope-transparency.md)
  ```
  with:
  ```markdown
  - Plan: [`alias-scope-transparency`](../changes/archive/2026-06-13.02-alias-scope-transparency/plan.md)
  ```

- [ ] **Step 4: Verify no live link still points at the old dirs**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  rg -n 'planning/specs/|planning/plans/|\.\./specs/|\.\./plans/' planning/releases/
  ```
  Expected: no output.

- [ ] **Step 5: Commit**

  ```bash
  git add planning/releases/
  git commit -m "docs: repoint release notes at the new change bundles

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 14: Add the `## Workflow` section to `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (insert a new section after `## Architecture`, before
  `## Code Style`)

- [ ] **Step 1: Insert the section**

  ```markdown
  ## Workflow

  Planning follows a portable two-axis convention (shared with
  `faststream-outbox`); full details in [`planning/README.md`](planning/README.md).

  - **`architecture/`** (repo root) is the **truth home** — living capability
    prose, the promotion target on every ship. The `## Architecture` section
    above is quick orientation; `architecture/` holds the authoritative,
    up-to-date account.
  - **`planning/changes/{active,archive}/<YYYY-MM-DD.NN-slug>/`** are change
    bundles: `design.md` + `plan.md` (full lane), or `change.md` (lightweight).
    Tiny changes (typo, dep bump, CI tweak) skip bundles entirely.
  - Templates live in [`planning/_templates/`](planning/_templates/).
  - **Shipping a change** hand-edits the affected `architecture/<capability>.md`,
    then moves the bundle from `active/` to `archive/` with `status: shipped`,
    `pr:`, and `outcome:` filled.
  ```

- [ ] **Step 2: Verify placement**

  Run: `rg -n '^## ' CLAUDE.md`
  Expected order: `Project Overview`, `Commands`, `Architecture`, `Workflow`,
  `Code Style`.

- [ ] **Step 3: Commit**

  ```bash
  git add CLAUDE.md
  git commit -m "docs: add Workflow section naming architecture/ as truth home

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 15: Promote this change & finalize frontmatter

This adoption is now shipping. Update the active bundle's own frontmatter and
move it to `archive/` (the Index already lists it under Active — update that too,
or leave the move for the merge step per the maintainer's preference).

- [ ] **Step 1: Decision checkpoint**

  Confirm with the maintainer whether to archive this bundle now (pre-merge) or
  on merge. Default: leave it in `active/` until the PR merges, then a follow-up
  commit moves it to `archive/2026-06-13.03-portable-planning-convention/`, sets
  `status: shipped` + `pr:` + `outcome:`, and moves its README Index line from
  Active to Archived. **No action this task if deferring to merge.**

---

### Task 16: Final verification

- [ ] **Step 1: Lint**

  ```bash
  cd /Users/kevinsmith/src/pypi/modern-di
  just lint-ci
  ```
  Expected: clean (eof-fixer + ruff format + ruff check + ty, no changes needed).

- [ ] **Step 2: Docs build (no-collateral-breakage check)**

  ```bash
  uv run mkdocs build --strict
  ```
  Expected: build succeeds. (`docs_dir: docs` excludes `planning/` and
  `architecture/`, so this confirms the migration didn't disturb the site. If
  `--strict` flags pre-existing unrelated warnings, drop `--strict` and confirm a
  plain build still succeeds.)

- [ ] **Step 3: No stray references to the removed dirs**

  ```bash
  rg -n 'planning/specs/|planning/plans/' --glob '!planning/changes/**'
  ```
  Expected: no output (frozen references inside bundles are intentionally
  excluded).

- [ ] **Step 4: Bundle integrity**

  ```bash
  find planning/changes -type f -name '*.md' | sort
  ```
  Expected: 17 archived files across 11 bundles + the active bundle's `design.md`
  and `plan.md`.

- [ ] **Step 5: Push and open the PR** (if the maintainer wants the PR now)

  ```bash
  git push -u origin chore/portable-planning-convention
  gh pr create --fill
  ```
