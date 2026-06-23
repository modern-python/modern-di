# Planning

Specs, plans, and change history for `modern-di`. The living truth about *what
the system does now* lives in [`architecture/`](../architecture/) at the repo
root; this directory records *how it got there*.

## Conventions

> This section is the portable convention — identical across the
> modern-python repos. The generated change listing (`just index`) and the `## Other` pointers below are repo-local. To adopt elsewhere,
> copy this section plus [`_templates/`](_templates/) and point that repo's
> `CLAUDE.md` Workflow + truth home at it.

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
one-liner). The implementing PR then sets `status: shipped` and fills `pr`
and `outcome` **in the branch**, alongside the code and the `architecture/`
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
- **`decisions.md`** — design decisions deliberately taken, especially options
  considered and *rejected*, each with a revisit trigger (an append-only log;
  promote to `decisions/<date>-<slug>.md` if it grows).

Templates live in [`_templates/`](_templates/).

### Frontmatter

`design.md` / `change.md`: `status` (draft|approved|shipped|superseded),
`date`, `slug`, `summary` (single line), `supersedes`, `superseded_by`, `pr`,
`outcome`. `plan.md`: `status`, `date`, `slug`, `spec`, `pr`. Files in
`architecture/` carry **no** frontmatter — living prose, dated by git.

## Index

The change listing is **generated**, not maintained — run `just index` to
print it (grouped by `status`: In progress / Shipped / Superseded). The
frontmatter in each bundle is the single source of truth; there is no
committed copy to drift.

## Other

- **[`architecture/`](../architecture/)** at the repo root — the living
  capability truth (scopes, containers, providers, resolution, validation,
  testing & overrides). This is the promotion target on every ship.
- **[audits/](audits/)** — findings reports (2026-06-05 bug-hunt, 2026-06-12
  code+docs, 2026-06-13 docs-ux, 2026-06-14 deep audit).
- **[deferred.md](deferred.md)** — real-but-unscheduled items with revisit
  triggers.
- **[decisions.md](decisions.md)** — design decisions taken (and alternatives
  rejected), so reviews don't re-litigate them.
- **[scripts/bug-hunt-audit.workflow.mjs](scripts/bug-hunt-audit.workflow.mjs)**
  — repo-specific extra (the reusable audit harness), not part of the portable
  core.
