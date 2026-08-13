# Planning

The standing record for `modern-di`. The living truth about *what the system
does now* lives in the code itself and in its tests — an enforceable claim is an
`INVARIANT:`-marked test, not a prose page. This directory holds what code and
tests cannot: the decisions taken (especially the options rejected) and the
work deliberately not scheduled.

> **Local deviation.** This repo tracks the portable convention from
> [`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
> (applied version in `.convention-version`, beside this file), but currently
> **deviates from it** on four counts: `changes/`, `audits/`, and `retros/` were
> removed; the per-change spec moved into the PR body; decision frontmatter lost
> its `status` and `supersedes` keys; and `index.py` — a vendored file — was
> edited locally to match that schema. If the deviation holds, it goes upstream
> as convention 3.0.0 and is re-applied via that repo's `APPLY.md` flow. See
> [`deferred/2026-07-29-upstream-lean-convention.md`](deferred/2026-07-29-upstream-lean-convention.md)
> for the open question and its revisit trigger.

## Quick path (start here)

**1. Write the spec in the PR body.** `.github/PULL_REQUEST_TEMPLATE.md` carries
the shape — why, design, trade-offs, and the non-goals. There is no change file
to write and nothing to commit: the PR body *is* the spec, reviewed inline with
the diff. A trivial PR (typo, dep bump, formatter, mechanical rename) may delete
the template and ship a conventional-commit title.

**2. File what outlives the PR:**

- an alternative you **rejected** with reasoning → `decisions/`
- work that is real but **not scheduled** → `deferred/`

**3. Run `just check-planning` and `just check-links` before pushing.**

## Where a fact goes

Four homes, one owner each:

| Home | Holds |
|---|---|
| `modern_di/` | anything readable from the module — the default |
| a named test | an **invariant**: must stay true, and a change could silently break it |
| `decisions/` | a rejected alternative, with the reasoning that would otherwise be re-litigated |
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

`decisions/` and `INVARIANT:` docstrings inherit the same risk from the other direction: nothing yet
prunes a record once its call is settled or a docstring once its claim stops mattering, so keeping
either lean is a habit this project owes them now, not a one-time fix earned by deleting a directory.

An invariant is written as a test whose name is the claim, with a docstring opening
`INVARIANT:` and a second paragraph naming **what breaks it**. That second paragraph
is where an anti-refactor warning lives — design rationale, not a report of what this
one test happens to catch. It does not have to describe a regression that *this*
test alone would fail on; a sibling test may be the one that actually trips. The unit
of truth is the invariant plus the whole suite, not the docstring plus its single
test — the accepted cost is that a reader cannot tell, from one docstring alone,
whether that test or a sibling one catches a given regression.
`tests/test_invariant_census.py` enforces the shape and checks that every test name or
path cited from a `modern_di/`, `tests/`, `CLAUDE.md`, or `planning/decisions/`/`planning/deferred/`
comment or docstring resolves to something real.

## What lives where

A shipped change leaves two traces, none of them a file in this directory: the diff
and the PR body. Between them they answer *what changed* and *why*.

`planning/` holds only what those two cannot:

- **`decisions/` — what was decided against.** A rejected alternative leaves no
  trace in a diff (the code that was not written) and isn't an enforceable claim
  (there's nothing to assert). Without a home it gets re-proposed.
- **`deferred/` — what is waiting.** Real work, not scheduled. Nothing else in
  the repo records the absence of something.

If a fact fits in code, a test, the diff, or the PR body, it goes there instead.
This directory is the residue, and it should stay small.

## Artifacts

- **[`decisions/<YYYY-MM-DD>-<slug>.md`](decisions/)** — one file per design
  decision taken, especially options *rejected*, each with a revisit trigger, so
  reviews don't re-litigate them. Frontmatter: `summary`, plus `superseded_by`
  once something supersedes it.
- **[`deferred/<YYYY-MM-DD>-<slug>.md`](deferred/)** — one file per open item,
  each **self-contained**: it inlines the evidence and reasoning needed to pick
  it up cold, and cites no report. Frontmatter: `summary`. A required
  `**Revisit trigger:**` section — an item with no trigger is abandoned, not
  deferred.
- **[`releases/<version>.md`](releases/)** — one file per curated release, from
  `_templates/release.md`. Used **verbatim** as the GitHub Release body by
  [`release.yml`](../.github/workflows/release.yml), which fails a stable tag
  that has no matching file. No frontmatter; the file name is the version.
- **[`_templates/`](_templates/)** — `decision.md`, `deferred.md`, `release.md`.
- **[`scripts/`](scripts/)** — reusable multi-agent audit harnesses. A sweep's
  durable output is a PR plus `deferred/` items; the report itself is transient
  and is not committed.

### Location is status

Neither artifact carries a `status:` field. Where a file sits, and which keys it
has, is what its state means.

A **deferred item's presence in `deferred/` is its status**. When it resolves:

- **it ships** → delete the file. Its truth is now in the code (or its tests)
  and the release notes.
- **it is declined** → move it to `decisions/`, so the refusal is on record.

A **decision is accepted unless it says otherwise**. There is no exit from
`decisions/` — a superseded decision stays readable, or it gets re-litigated —
so the one state worth recording is marked by adding `superseded_by: <slug>`,
which `just index` renders. Absent means accepted. The inverse `supersedes` key
is gone: it is derivable, and two pointers per relationship is one too many to
keep honest.

`date` and `slug` are derived from the file name and never repeated in
frontmatter. `summary` is one line; it is the only field the index renders for
an ordinary entry.

## Index

The listing is **generated**, not maintained — run `just index` to print it:
deferred first (the open queue), then decisions, newest-first. The frontmatter in
each file is the single source of truth; there is no committed copy to drift.
`just check-planning` validates it, and `just check-links` validates every
relative Markdown link and heading anchor in the repo — including the trees a
site builder never sees.
