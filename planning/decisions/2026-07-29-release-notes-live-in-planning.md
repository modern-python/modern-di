---
summary: Release notes live in `planning/releases/`, not `docs/changelog/` — reversing the move made in #394. The docs site links to the directory instead of republishing 25 pages, trading site search and llms.txt inclusion for one home per artifact.
---

# Release notes live in `planning/releases/`, not the docs site

**Decision:** Curated release notes are committed at `planning/releases/<version>.md`
and are **not** published as docs-site pages. `docs/changelog.md` is a single page
carrying one outbound link to the GitHub directory. This reverses the move made in
[#394](https://github.com/modern-python/modern-di/pull/394), which had relocated
them from `planning/releases/` to `docs/changelog/`.

## Context

#394 moved the notes into `docs/`, edited several to read as user-facing prose,
rewired `release.yml` to read `docs/changelog/<tag>.md`, and added
`mkdocs_hooks.py` to generate the changelog nav at build time so a new release
needed no `mkdocs.yml` edit. That move was never recorded in `decisions/`, which is
why it was re-litigable at all.

The seam that reopened it: `planning/_templates/release.md` produced output in
`docs/`. A template in one tree writing into another is a small thing, but it has
exactly two fixes, and they point in opposite directions.

- **Close it from the docs end.** Leave the notes published, move the template to
  `docs/`. Costs nothing user-visible.
- **Close it from the planning end.** Move the notes back, template and output
  reunited under `planning/`. Costs the published pages.

A third option — keep the notes in `planning/` and symlink them into `docs/` so
mkdocs still publishes them — was rejected outright: a symlink is a third mechanism
to maintain so that two directories can disagree about where a file lives, and it
would have to survive CI checkouts, Windows, and `links.py`.

## Decision & rationale

The notes move back. The maintainer-facing argument won: a release note is written
by a maintainer, from a template that lives in `planning/`, and consumed verbatim
by `release.yml`. Having one home for the artifact and its template beats having
the artifact rendered in two places.

**The cost is real and was accepted with it stated.** `mkdocs.yml` has one plugin
(`llmstxt`) and mkdocs cannot serve files outside `docs_dir`, so 25 pages left the
published site, its search index, and `llms-full.txt`. A user reading the changelog
now leaves the docs site to do it. `mkdocs_hooks.py` and `tests/test_mkdocs_hooks.py`
were deleted as dead code.

The curated `index.md` — 26 one-line release headlines — was deleted rather than
relocated to `planning/releases/README.md`. A README there would have been rendered
by GitHub at the exact destination the docs link points to, which is the better
landing page; it was declined because it is hand-maintained, so every release would
add a line to it. That is the recurring chore `mkdocs_hooks.py` had been written to
eliminate, and re-introducing it by hand was judged worse than a bare file listing.

This deepens the tension in `planning/README.md`'s own charter — that the directory
"holds only what `architecture/`, the diff, and the PR body cannot" and "should stay
small." Release notes are none of those three, and at 25 files they outnumber
`decisions/` (24) and `deferred/` (10). The charter language was left as-is because
the counter-argument is that `releases/` is a fourth artifact kind with its own
lifecycle, not residue; if that stops feeling true, the charter is what should
change, not this decision.

## Revisit trigger

Any of three signals:

- **A user asks where the changelog went**, or an issue/discussion shows someone
  failed to find release notes from the docs site. That is the regression becoming
  concrete rather than theoretical.
- **`mkdocs.yml` gains a plugin that can publish from outside `docs_dir`** (e.g.
  `mkdocs-monorepo`, `gen-files`, `literate-nav`) for an unrelated reason — the
  cost of publishing the notes would then be near zero and the trade-off changes.
- **`planning/` stops being scannable.** `releases/` grows monotonically and never
  gets pruned; if the directory becomes hard to read, splitting it back out is the
  first thing to reconsider — see
  [`../deferred/2026-07-29-upstream-lean-convention.md`](../deferred/2026-07-29-upstream-lean-convention.md),
  which already tracks `decisions/` + `deferred/` growth against a baseline.
