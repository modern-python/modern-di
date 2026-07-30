# Planning

The standing record for `modern-di`. The living truth about *what the system
does now* lives in [`architecture/`](../architecture/) at the repo root; this
directory holds what `architecture/` cannot: the decisions taken (especially the
options rejected) and the work deliberately not scheduled.

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

**2. Promote in the same PR.** If the change alters a capability's behavior,
hand-edit the matching `architecture/<capability>.md` in the same diff, so the
edit is reviewed with the code. That promotion is what keeps `architecture/`
true.

**3. File what outlives the PR:**

- an alternative you **rejected** with reasoning → `decisions/`
- work that is real but **not scheduled** → `deferred/`
- a term worth pinning down → `architecture/glossary.md`

**4. Run `just check-planning` and `just check-links` before pushing.**

## What lives where

A shipped change leaves three traces, none of them a file in this directory: the
diff, the updated capability page in [`architecture/`](../architecture/), and the
PR body. Between them they answer *what changed*, *what is true now*, and *why*.

`planning/` holds only what those three cannot:

- **`decisions/` — what was decided against.** A rejected alternative leaves no
  trace in a diff (the code that was not written) and does not belong in
  `architecture/` (it is not current behaviour). Without a home it gets
  re-proposed.
- **`deferred/` — what is waiting.** Real work, not scheduled. Nothing else in
  the repo records the absence of something.

If a fact fits in `architecture/`, the diff, or the PR body, it goes there
instead. This directory is the residue, and it should stay small.

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
- **[`scripts/`](scripts/)** — reusable audit and data-collection harnesses. A
  sweep's durable output is a PR plus `deferred/` items; the report itself is
  transient and is not committed. A collector's output is likewise transient:
  it regenerates on demand and carries no committed artifact of its own.

### Location is status

Neither artifact carries a `status:` field. Where a file sits, and which keys it
has, is what its state means.

A **deferred item's presence in `deferred/` is its status**. When it resolves:

- **it ships** → delete the file. Its truth is now in `architecture/` and the
  release notes.
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
