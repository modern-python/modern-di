---
summary: The `architecture/` directory is deleted; its facts route to code, a named test, `planning/decisions/`, or `docs/` instead of a prose page that restates the code and drifts.
---

# Drop the `architecture/` directory

**Decision:** `architecture/` is deleted. What it used to carry now routes to one of four homes: an
enforceable claim becomes an `INVARIANT:`-marked test guarded by `tests/test_invariant_census.py`; a
negative contract (something deliberately *not* guaranteed) becomes a `planning/decisions/` record; a
framework-facing contract moves to `docs/`; a term worth pinning down that isn't fully derivable from
code stays in whatever residual glossary form `planning/` ends up using. Nothing is promoted to a
standalone prose "truth home" page again.

## Context

`architecture/` was 11 prose pages, one per capability, meant to be the living, code-current account of
the library's behaviour — the `CLAUDE.md` at the repo root called it out as "quick orientation only...
the authoritative, code-current account of each capability." The convention was: a behaviour change
hand-edits the matching capability page in the same PR, and a checklist item asked reviewers to confirm
that happened.

That promotion discipline **worked** — PRs did update the pages. It just didn't work in the direction
that keeps a doc small. Two prior attempts tried to correct the resulting bloat by cutting the pages
back down rather than questioning whether the pages should exist at all:

- **`b2404c4`** (#282, 2026-07-07, "docs: trim architecture/ to charter — invariants only") — a
  433-line net cut.
- **`047b6ea`** (#395, 2026-07-29, "docs(architecture): thin resolution.md to invariants; one owner per
  concept") — a 292-line net cut from `resolution.md` alone.

Both regrew. `resolution.md` — a 175-line file at the point this decision was made — accumulated
+617/−442 lines across 23 commits since it existed; a page trimmed twice still ended up net-larger than
either trim removed. Contrast `glossary.md`, which took +93/−4 across only 2 commits: a page that
mostly just gets written once and referenced, not continuously re-edited to track behaviour, doesn't
have this problem at all. The asymmetry is the tell — it isn't that contributors write bloated prose in
general, it's specifically the pages the promotion checklist forces continuous re-editing of.

## Decision & rationale

**The promotion discipline was not the failure — it was working exactly as designed, and that's the
problem.** Measured at the branch point for this change: of the 67 commits touching `modern_di/` since
mid-June, 48 also touched `architecture/` — 72%. That's a *high* compliance rate with "did you update
the page?" The checklist item that drove it only ever asked that one question. It never asked "should
this paragraph exist?" So every PR that touched behaviour had a structural incentive to *add* a
sentence explaining the new behaviour, and no PR had any correspondent incentive to *remove* a sentence
whose enforcement value had already been captured elsewhere — in a test, in a type signature, in the
code itself being self-evident on read. Addition-without-subtraction, run for weeks across dozens of
compliant PRs, is exactly the churn profile `resolution.md` shows.

Tasks 1–4 of this branch already did the harder part of the fix: they read the 11 pages, found the
claims that were actually enforceable, and turned 30 of them into `INVARIANT:`-marked tests. A test
regresses automatically when it stops being true; a prose paragraph doesn't. That converts "the page
still says X" from a discipline problem back into a mechanical one.

**What's left — five records in this file's cohort — could not go into a test**, because their entire
content is the *absence* of a guarantee: no assertion follows from "the library does not promise this
order" or "this value is not type-checked." Deleting the page without capturing them would silently
turn each into either an unfixed bug report (someone "fixes" the unspecified transient teardown order)
or an unsupported reliance (someone starts depending on override values being type-checked because
nothing said otherwise). `planning/decisions/` is the right home because these are exactly what that
directory is for: options considered and a call made, with reasoning a future explorer would otherwise
re-litigate.

**Rejected alternative: keep a smaller `architecture/`.** This is the option the two prior thinnings
already tried, twice, and it regrew both times. A third attempt with a stricter charter has no reason
to fare differently unless the underlying incentive changes — and the underlying incentive is the
promotion checklist itself, which this decision removes rather than tightens.

**Rejected alternative: turn the glossary into a decision record.** A glossary is consulted *while
writing* — a contributor mid-PR needs to know what `bound_type` means right now, inline with the code
they're editing. A decision record is consulted *while deciding* — before writing, to check whether an
option was already rejected. Those are different reading moments; collapsing them into one file type
would serve neither well.

**Rejected alternative: drop the glossary entirely, relying on code and docstrings.** Rejected because
the glossary's `Avoid:` entries — the deliberately-not-used synonyms for a term, and why — are not
derivable from reading the code. Code shows what a name *is*; it doesn't show what a contributor
*almost* called it instead and why that was wrong. That negative information has nowhere else to live.

## Revisit trigger

An invariant is found that has no test form (nothing to assert), no decision form (it isn't a call
between rejected alternatives — it's simply a fact worth stating), and is needed by more than one
reader. A single such fact is better placed in the nearest docstring or `docs/` page; a *pattern* of
such facts, recurring enough that they'd naturally cluster into one file again, is the signal that a
`architecture/`-shaped truth home is needed after all — and if that happens, the fix this time is a
charter that states what does *not* belong on the page, not just what does.
