---
summary: Whether the lean convention (no `changes/`, no `audits/`, spec in the PR body) goes upstream as planning-convention 3.0.0 — the harvest suggests it only pays off in a repo that already promotes reliably, which is a reason to soak longer than first planned.
---

# Upstream the lean convention, or keep it a local deviation

`modern-di` currently **deviates** from
[`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
2.2.0 (the applied version in `planning/.convention-version`): `changes/`,
`audits/`, and `retros/` are gone, and the per-change spec lives in the PR body.
The plan was to prove it here for a few weeks, then cut 3.0.0 upstream and
re-apply via that repo's `APPLY.md` flow.

## Why it is open

**The harvest changed the argument for it.** The premise going in was that change
files hold nothing durable. That held — 113 change files plus 18 audit reports
yielded only 3 promotions to `decisions/`. But the *reason* was not the predicted
one. The why-nots were not missing from `changes/`; they had **already been
promoted** into `architecture/`, `ROADMAP.md`, `benchmarks/README.md`, and
`docs/introduction/design-decisions.md` at ship time. Of the 33 files examined,
16 were redundant because their content had been promoted or already had a
`decisions/` file.

That is a conditional result, not a general one. Deleting `changes/` is safe
**because promotion discipline works here**. In a repo where the
promote-in-the-same-PR rule is followed loosely, the change files are the only
record, and deleting them destroys information rather than removing a duplicate.

So the honest upstream question is not "does this work" but "what does a repo need
to be true of itself before this is safe" — and 3.0.0 would ship it to consumers
who may not meet that bar. Three routes:

1. **Soak longer here**, then upstream as 3.0.0 with a stated precondition:
   adopt only if your `architecture/` promotions are reliable.
2. **Upstream as an optional profile** alongside the current one, so repos choose.
   This was considered when the plan was made and passed over; the harvest is an
   argument to reconsider it.
3. **Keep it a permanent local deviation** — drop `.convention-version` and the
   portability language, accept the loss of shared vocabulary across the org's
   repos.

Two things should inform whichever route is taken, and neither has evidence yet:

- Whether writing specs in PR bodies actually holds up over a month of real
  changes, or quietly degrades into thin descriptions because nothing in the repo
  enforces the shape the way `check-planning` enforced change-file frontmatter.
- Whether `decisions/` and `deferred/` grow at a rate that keeps them scannable.
  They are 24 and 11 files now; the value of the whole design rests on them
  staying small enough to read.

## Revisit trigger

After roughly a month of real changes under the new convention (so, from
late August 2026) — with two checks before deciding: re-read the last ten merged
PR bodies and judge whether they are specs or descriptions, and count
`decisions/` + `deferred/` against the 24 + 11 baseline recorded here.
