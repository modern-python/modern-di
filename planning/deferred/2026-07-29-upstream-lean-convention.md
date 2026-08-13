---
summary: Whether the lean convention (no `changes/`, no `audits/`, spec in the PR body, and now a slimmed decision frontmatter with a locally forked `index.py`) goes upstream as planning-convention 3.0.0 — the harvest suggests it only pays off in a repo that already promotes reliably, which is a reason to soak longer than first planned.
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
promoted** into `architecture/` (since removed — see the note below),
`ROADMAP.md`, `benchmarks/README.md`, and `docs/introduction/design-decisions.md`
at ship time. Of the 33 files examined,
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
   adopt only if your capability-documentation promotions are reliable
   (`architecture/` was this repo's version of that target; see the note below).
2. **Upstream as an optional profile** alongside the current one, so repos choose.
   This was considered when the plan was made and passed over; the harvest is an
   argument to reconsider it.
3. **Keep it a permanent local deviation** — drop `.convention-version` and the
   portability language, accept the loss of shared vocabulary across the org's
   repos.

## The second axis: the schema fork

The deviation was layout-only when this item was filed. It is not any more.
Decision frontmatter dropped `status` and `supersedes`, keeping `summary` plus an
optional `superseded_by` whose *presence* means superseded — matching how
`deferred/` already treats location as status. That required editing
`planning/index.py`, which line 1 declares is **vendored into consumers'
`planning/`**. So this repo's copy of the tooling now differs from upstream
2.2.0, not just its directory layout.

That widens the upstream question rather than changing its answer. A layout
deviation is something a consumer opts into by reading a README; a vendored-file
deviation is something that silently loses their edits the next time `APPLY.md`
re-vendors. Whichever route is taken, the schema has to travel with it or be
reverted — the two cannot ship apart.

It also strengthens route 2 (an optional profile). The frontmatter change is
cheap to make optional — `DECISION_REQUIRED` is one tuple — in a way that
deleting `changes/` is not.

Three things should inform whichever route is taken, and none has evidence yet:

- Whether writing specs in PR bodies actually holds up over a month of real
  changes, or quietly degrades into thin descriptions because nothing in the repo
  enforces the shape the way `check-planning` enforced change-file frontmatter.
- Whether `decisions/` and `deferred/` grow at a rate that keeps them scannable.
  They are 24 and 7 files as of 2026-07-30; the value of the whole design rests
  on them staying small enough to read.
- Whether `superseded_by` is ever actually written. In 24 decisions the old
  `status` field never once took its second value. If a year passes with no
  supersession, the honest conclusion is that `decisions/` needs no state marker
  at all and the key should go too.

## Update: the promotion target this item relied on is gone

`architecture/` was deleted 2026-08-11
([`2026-08-11-drop-architecture-directory.md`](../decisions/2026-08-11-drop-architecture-directory.md)):
11 capability pages routed instead to code, a named `INVARIANT:`-marked test,
`decisions/`, or `docs/`, per the four-homes admission check now in
`planning/README.md`. The premise this item's central finding rested on —
deleting `changes/` was safe *because* `architecture/` promotion discipline
worked — is no longer demonstrable the same way, because the thing being
promoted *into* no longer exists as a single directory to point at.

This does not resolve the upstream question; if anything it sharpens it. The
harvest's finding still holds as a historical fact (16 of 33 examined files
were redundant because their content had already reached a durable home by ship
time). But route 1's phrasing above — "adopt only if your `architecture/`
promotions are reliable" — no longer names a target this repo still has. A
2.30.0-vintage answer would need to generalize it to "adopt only if your
capability facts reliably reach *some* durable home (code, tests,
`decisions/`, `docs/`)," which is the four-homes model this repo now runs, not
the two-destination one (`architecture/` and everything else) the harvest was
measured against. Whether that generalized claim holds needs its own evidence;
none exists yet. The revisit trigger below is unchanged — this update narrows
what "check" means but does not move the date.

## Revisit trigger

After roughly a month of real changes under the new convention (so, from
late August 2026) — with three checks before deciding: re-read the last ten
merged PR bodies and judge whether they are specs or descriptions; count
`decisions/` + `deferred/` against the 24 + 7 baseline recorded here; and diff
`planning/index.py` and `planning/links.py` against upstream 2.2.0 to see how far
the vendored files have drifted.
