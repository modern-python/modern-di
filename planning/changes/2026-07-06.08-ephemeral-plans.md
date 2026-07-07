---
summary: Convention v1.2.0 — plans become ephemeral executor scratch; Full-lane bundles commit design.md only; the 28 committed plan.md files are deleted from HEAD.
---

# Design: Ephemeral plans — lean change bundles

## Summary

The planning convention (canonical repo `lesnik512/planning-convention`) gains
a 1.2.0 release that removes `plan.md` from change bundles: the Full lane
commits `design.md` only, and the executable plan becomes git-ignored working
scratch for whatever executor skill runs it. modern-di then applies the update
(1.0.0 → 1.2.0) and deletes its 28 committed `plan.md` files from HEAD.

## Motivation

A verbosity benchmark of this repo against 7 comparable libraries (2026-07-06)
found `planning/` is 137k words — 4.5x the entire user docs site — and that
`plan.md` files (~45k words) are 75–90% duplication: embedded test and
implementation code that becomes the shipped diff, per-task commit blocks whose
subjects appear verbatim in `git log`, and gate-restating checklists. No
surveyed project keeps an analog in-repo.

Root cause: superpowers `writing-plans` deliberately produces self-contained
plans (complete code in every step) because `subagent-driven-development` hands
each fresh implementer only its own task brief. Those are execution artifacts.
Routing them into `planning/changes/*/plan.md` turned them into permanent
history, where they duplicate the git record they produce. Recent bundles
(2026-07-06.01–.07, 369–717 words vs the June median of ~2,300+) already show
the lean shape loses nothing — the PR carries the execution record.

## Design

### 1. Canonical repo → 1.2.0

- **`convention.md`**: Full lane = `design.md` only. New prose: plans are
  ephemeral (git-ignored scratch, e.g. `.superpowers/`, in whatever format the
  executor needs; never committed — git history and the PR are the record of
  execution). Lean-spec rules: design.md is the single home of rationale (the
  PR body summarizes and links, never restates); rejected alternatives live in
  `decisions/` and are referenced, not retold; sketches allowed, full
  diff-to-be forbidden; template sections that don't apply are deleted; soft
  guidance that most designs fit under ~700 words. Lanes table, Quick path,
  and Artifacts-at-a-glance updated. `change.md` lane unchanged, but its
  template's outgrow sentence now targets a `design.md` only.
- **`_templates/`**: delete `plan.md`; rewrite `design.md` (fold the
  overlapping Non-goals / Out of scope sections into one, bake the lean rules
  into placeholder text).
- **`index.py`**: remove `"plan.md"` from `ALLOWED_BUNDLE_FILES` — a committed
  plan then fails `--check` as an unexpected file. Update the pytest suite
  (100% coverage gate) and the CI fixture.
- **`APPLY.md`**: §1 notes the `plan.md` template deletion propagates to
  consumers, and one line permitting consumers' placeholder fills in
  `release.md` (today's wording clobbers them on every update).
- **`CHANGELOG.md`**: 1.2.0 entry; tag after merge.

### 2. modern-di — apply 1.0.0 → 1.2.0

APPLY.md UPDATE flow on a branch: verbatim-copy `index.py` and `_templates/`
(drops `plan.md`, adds 1.1.0's `glossary.md`), merge the new convention prose
into `planning/README.md` (repo-local `## Index` / `## Other` kept), delete
the 28 `changes/*/plan.md` files (git history preserves them), keep the
repo-local `release.md` fills, bump `.convention-version`, PR listing the
applied deltas. `architecture/glossary.md` stays lazy — authored when the
first term is worth pinning down.

## Non-goals

- No rewriting of existing `design.md` prose or `audits/` / `retros/` genres.
- No change to the superpowers execution flow — fat plans remain correct as
  scratch; only their committed fate changes.
- The docs/ dedupe, docstring cleanup, and `architecture/` halving from the
  same benchmark are separate follow-up changes.

## Testing

- Canonical: `python3 index.py --check` green; pytest suite covers the
  `plan.md` rejection (a bundle containing `plan.md` yields the
  unexpected-file violation); CI fixture updated.
- modern-di: `just check-planning` prints `planning: OK` with plans deleted;
  `just lint-ci` passes; `just index` renders unchanged summaries.

## Risk

- Other consumers of the convention fail `--check` on their next update until
  they delete/ignore committed plans — intended, and the CHANGELOG entry is
  the migration note. Low impact: consumers update deliberately via APPLY.md.
- Losing in-tree visibility of past task sequencing — accepted; the audit
  showed it duplicates git/PR history, and `git log --follow` recovers it.
