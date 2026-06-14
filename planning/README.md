# Planning

Specs, plans, and change history for `modern-di`. The living truth about *what
the system does now* lives in [`architecture/`](../architecture/) at the repo
root; this directory records *how it got there*.

## Conventions

> This section is the portable convention — identical across the
> modern-python repos. The Index below is repo-specific. To adopt elsewhere,
> copy this section plus [`_templates/`](_templates/) and point that repo's
> `CLAUDE.md` Workflow + truth home at it.

### Two axes, never mixed

- **`architecture/` (repo root) — the present.** One file per capability,
  living prose, updated whenever a change ships. The truth home.
- **`planning/changes/` — the past-and-pending.** One folder per change,
  frozen once shipped.

Shipping a change **promotes** its conclusions into the affected
`architecture/<capability>.md` by hand, then archives the bundle. That
hand-edit is what keeps `architecture/` true; the archived bundle carries the
*why*.

### Change bundles

A change is a folder `changes/active/YYYY-MM-DD.NN-<slug>/`:

- `YYYY-MM-DD` — proposal date; `.NN` — zero-padded intra-day counter
  (`.01`, `.02`, …) that breaks same-date ties so the timeline sorts stably.
- `<slug>` — kebab-case description, not a story ID.

On merge the folder moves to `changes/archive/` with `status: shipped`, `pr:`,
and `outcome:` filled, and its line moves from **Active** to **Archived** in
the Index below.

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

Templates live in [`_templates/`](_templates/).

### Frontmatter

`design.md` / `change.md`: `status` (draft|approved|shipped|superseded),
`date`, `slug`, `supersedes`, `superseded_by`, `pr`, `outcome`.
`plan.md`: `status`, `date`, `slug`, `spec`, `pr`. Files in `architecture/`
carry **no** frontmatter — living prose, dated by git.

## Index

### Active

- **[set-context-cross-scope-staleness](changes/active/2026-06-14.02-set-context-cross-scope-staleness/design.md)**
  (2026-06-14) — Resolve `ContextProvider` params live so a late `set_context`
  always propagates (cross-scope, non-cached); delete dead
  `invalidate_compiled_kwargs`; document the cached-factory limitation. From the
  2026-06-14 deep audit (sole ship-blocker). Full lane.

### Archived (shipped)

- **[portable-planning-convention](changes/archive/2026-06-13.03-portable-planning-convention/design.md)**
  (#210, 2026-06-13) — Adopt the two-axis convention: `architecture/` truth +
  `changes/` bundles + portable README, copied from faststream-outbox.
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
