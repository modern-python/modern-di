# Planning

The standing record for `modern-di`. The living truth about *what the system
does now* lives in the code itself and in its tests — an enforceable claim is an
`INVARIANT:`-marked test, not a prose page. This directory holds what code and
tests cannot.

## Quick path (start here)

**1. Write the spec in the PR body.** `.github/PULL_REQUEST_TEMPLATE.md` carries
the shape — why, design, trade-offs, and the non-goals. There is no change file
to write and nothing to commit: the PR body *is* the spec, reviewed inline with
the diff. A trivial PR (typo, dep bump, formatter, mechanical rename) may delete
the template and ship a conventional-commit title.

**2. File what outlives the PR:**

- an alternative you **rejected** with reasoning → an ADR in
  [`docs/adr/`](../docs/adr/), numbered `NNNN-slug.md`
- work that is real but **not scheduled** → `deferred/`

**3. Run `just check-links` before pushing.**

## Where a fact goes

Four homes, one owner each:

| Home | Holds |
|---|---|
| `modern_di/` | anything readable from the module — the default |
| a named test | an **invariant**: must stay true, and a change could silently break it |
| `docs/adr/` | a rejected alternative, with the reasoning that would otherwise be re-litigated |
| `docs/` | anything a user needs |

Before writing a line anywhere:

> Can an agent get this by reading `modern_di/`? → **don't write it.**
> Would a wrong change here fail a test? → it belongs **in the test**, not in prose.
> Does a user need it? → **`docs/`**.
> Otherwise it does not get written.

**Prose about mechanism has no home. There is no file to add a paragraph to.**

This is deliberate, and it is the second lesson rather than the first. A capability
directory (`architecture/`) was kept for four months and cut to invariants twice —
`b2404c4` (#282, 2026-07-07: 433 deletions against 110 insertions across six pages)
and `047b6ea` (#395, 2026-07-29: 292 against 147 across four) — and regrew both
times. Promotion discipline was not the problem: 72% of commits touching
`modern_di/` also touched it. Every PR added a paragraph that felt load-bearing and
none removed one, so the pages ratcheted toward restating code, and restatement is
what goes stale. The absence of the directory is the mechanism.

ADRs and `INVARIANT:` docstrings inherit the same risk from the other direction:
nothing prunes a record once its call is settled or a docstring once its claim stops
mattering, so keeping either lean is a standing habit, not a one-time fix.

An invariant is written as a test whose name is the claim, with a docstring opening
`INVARIANT:` and a second paragraph naming **what breaks it**. That second paragraph
is where an anti-refactor warning lives — design rationale, not a report of what this
one test happens to catch. It does not have to describe a regression that *this*
test alone would fail on; a sibling test may be the one that actually trips. The unit
of truth is the invariant plus the whole suite, not the docstring plus its single
test — the accepted cost is that a reader cannot tell, from one docstring alone,
whether that test or a sibling one catches a given regression.
`tests/test_invariant_census.py` enforces that shape.

## Artifacts

- **[`deferred/<YYYY-MM-DD>-<slug>.md`](deferred/)** — one file per open item,
  each **self-contained**: it inlines the evidence and reasoning needed to pick
  it up cold. A required `**Revisit trigger:**` section — an item with no trigger
  is abandoned, not deferred. This directory is being retired in favour of GitHub
  Issues; do not add to it.
- **[`releases/<version>.md`](releases/)** — one file per curated release, from
  `_templates/release.md`. Used **verbatim** as the GitHub Release body by
  [`release.yml`](../.github/workflows/release.yml), which fails a stable tag
  that has no matching file. No frontmatter; the file name is the version.
- **[`_templates/`](_templates/)** — `release.md`.
- **[`scripts/`](scripts/)** — reusable multi-agent audit harnesses. A sweep's
  durable output is a PR plus an issue or an ADR; the report itself is transient
  and is not committed.
- **`links.py`** — repo-wide Markdown link and heading-anchor check, run by
  `just check-links` and by `just lint-ci`. It covers the trees a site builder
  never sees.

A **deferred item's presence in `deferred/` is its status**. When it resolves: if
it ships, delete the file (its truth is now in the code and the release notes); if
it is declined, write the refusal as an ADR under [`docs/adr/`](../docs/adr/).
