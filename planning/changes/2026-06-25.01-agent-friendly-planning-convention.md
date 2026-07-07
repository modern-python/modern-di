---
summary: Make the planning convention agent-friendly — progressive-disclosure restructure (Quick-path on-ramp, deterministic lane decision, de-duplicated text) plus a `just check-planning` validator.
---

# Design: Make the planning convention agent-friendly

## Summary

The portable two-axis planning convention works, but it was written for human
readers and is awkward for an agent to consume: the lane rules are a prose table
the agent must self-apply before it knows the final diff, the convention text is
duplicated across CLAUDE.md and `planning/README.md`, and every invariant
(frontmatter keys, shipped-bundle completeness, no committed scratch) is enforced
only by diligence. This change restructures the convention text into three
explicit progressive-disclosure tiers and adds a machine-checkable validator. It
does **not** alter the two-axis model, the three lanes, frontmatter fields, or
`architecture/`. Scope is the **portable** convention: the changes are written to
be copied verbatim to sibling modern-python repos (rollout there is a separate
per-repo step).

## Motivation

A 2026-current best-practice sweep (Anthropic context-engineering guidance, the
SDD tooling convergence around spec-kit/Kiro, the AGENTS.md + agent-skills
progressive-disclosure pattern) all point the same way: orient an agent with a
minimal entry point, push detail behind it, and replace prose diligence with
machine-checkable guardrails. Read against that bar, four concrete frictions
stand out (numbering matches the evaluation that produced this spec):

1. **No machine-checkable validation.** Frontmatter keys, valid `status`,
   shipped bundles having an `outcome`, `plan.md`'s `spec:` resolving, and "no
   scratch files committed" are all enforced by hand. The 2026-06-23 retro
   records these exact failures (a subagent force-committed
   `.superpowers/sdd/*-report.md`; decisions-lane frontmatter churn). `index.py`
   already parses frontmatter but never validates it.
2. **The convention is duplicated.** CLAUDE.md `## Workflow` re-describes the
   lanes/bundles/decisions that `planning/README.md` "Conventions" already
   defines. An agent reads the lane rules twice, and the two copies can drift —
   worse across the portable set.
4. **Lane selection is prose criteria, not a procedure.** Choosing a lane is the
   single most frequent decision an agent makes, but the rule is a criteria table
   it must apply *before* the final LOC/file count exists. Agents follow explicit
   first-match decision trees far more reliably than threshold prose.
5. **No cheap on-ramp.** There is no ~15-line "you are here → pick a lane →
   create a bundle → ship" path; an agent must read the full ~100-line Conventions
   section even for a tiny change. That is the missing top tier of progressive
   disclosure.

(Findings 3, 6, 7, 8 from the evaluation — promotion-enforcement heuristic,
EARS-style acceptance criteria, a consolidated finishing checklist, an `.NN`
helper — are deliberately deferred; see Non-goals.)

## Non-goals

- Not changing the two-axis model (`architecture/` truth + `changes/` bundles).
- Not changing the three lanes themselves, their thresholds, or frontmatter
  fields — only how the lane choice is *presented*.
- Not touching `architecture/`, `_templates/` content, `audits/`, `retros/`,
  `releases/`, or `decisions/` structure.
- Not implementing findings 3/6/7/8 (promotion heuristic, EARS acceptance
  criteria, finishing checklist, `.NN` helper). Each can come later.
- Not rolling the changes into sibling repos in this PR — see Operations.

## Design

### 1. Three progressive-disclosure tiers (findings 2, 4, 5)

The convention text is reorganized into three tiers, each loaded only when
needed:

**Tier 1 — Quick path (the agent on-ramp).** A new section at the *top* of
`planning/README.md`, above the existing "Conventions". ~15 lines. It contains
the lane decision procedure, the minimal create→ship steps, and a pointer down to
the full reference. An agent doing a routine change reads only this; it never
needs the full spec for a tiny/lightweight change.

The lane decision becomes a deterministic, first-match-wins list (finding 4),
replacing the criteria table as the *primary* presentation:

```
Choose a lane — first matching rule wins:
1. Any of: needs design judgment · new file/module · public-API change ·
   cross-cutting or multi-file · non-trivial test design  → Full (design.md + plan.md)
2. Purely mechanical: typo · dep bump · linter/formatter/CI tweak ·
   mechanical rename · single-line config                 → Tiny (no bundle, commit only)
3. Small-but-real, none of the above: ≲30 LOC net · ≤2 files · no new file ·
   no public-API change · one straightforward test        → Lightweight (change.md)
Ambiguous between two? Take the heavier. A change.md that outgrows its lane
splits into design.md + plan.md.
```

Full-triggers-first ordering encodes "heavier wins on ambiguity": any Full
trigger short-circuits before the lighter lanes are considered.

**Tier 2 — Authoritative reference.** The existing "Conventions" section of
`planning/README.md` remains the single source of truth (bundle anatomy,
frontmatter spec, artifacts-at-a-glance, three-lane detail). **No content moves
out of it.** The existing three-lane table stays here as the detailed reference;
the Quick-path list is the procedural front door to it.

**Tier 3 — Templates.** `_templates/` is unchanged — loaded only when actually
writing an artifact.

**De-duplication (finding 2).** CLAUDE.md `## Workflow` currently re-describes
lanes/bundles/decisions. That duplicated prose is deleted and replaced by a
~6-line pointer to the Quick path. CLAUDE.md *keeps* the genuinely repo-specific
release-cutting process (tag-driven publish), which is not in the README. After
this, the lane rules exist in exactly one place.

### 2. `just check-planning` validator (finding 1)

Extend `planning/index.py` with a `--check` mode that reuses its existing
`parse_frontmatter` / `load_bundles` / `load_decisions`, exposed as a
`just check-planning` recipe and wired into `just lint-ci`. It collects all
violations, prints them, and exits non-zero if any. Keeping it inside `index.py`
holds the portable surface to a single script.

Checked invariants (all portable):

- **Bundle shape:** each bundle dir has a `design.md` or `change.md`; the dir
  contains **only** known artifacts (`design.md`, `plan.md`, `change.md`) —
  catches the retro's committed-scratch footgun.
- **Frontmatter completeness:** required keys present per artifact type —
  `design.md`/`change.md`: `date`, `slug`, `summary`, `outcome`; `plan.md`:
  `date`, `slug`, `spec`; `decisions/*.md`: `status`, `date`, `slug`, `summary`.
- **Field validity:** a decision's `status` ∈ {`accepted`, `superseded`}; `date`
  matches `YYYY-MM-DD`; the bundle dir name matches `YYYY-MM-DD.NN-slug` and its
  `slug` field agrees with the dir slug.
- **Link integrity:** `plan.md`'s `spec:` path resolves to an existing file
  (relative to the bundle dir).

(The field set above is the post-`status`/`pr` state — see the Updates section
below for how it got here.)

The validator reports *all* violations in one run (not fail-fast) so an agent or
human fixes the whole set at once.

### 3. Bootstrapping note

Running `--check` against the current repo may surface pre-existing violations in
historical bundles (e.g. a missing `outcome`, an unexpected file). Part of this
change is bringing the existing bundles to green — either by fixing the
frontmatter or, where a historical bundle is legitimately irregular, by making
the check's rule precise enough not to flag it. The executor records any such
fixes; the gate ships only once `just check-planning` is clean.

## Updates (2026-06-25, during execution)

### `pr` dropped from the convention

The original plan required `status: shipped ⇒ pr + outcome` and backfilled `pr`
across 15 historical bundles. Doing that backfill exposed why `pr` is the wrong
field to enforce: it is the only frontmatter value that is hand-supplied,
knowable only *after* the PR exists (so it is always a second edit and blocks
marking a bundle shipped until then), **and** already recoverable from git (the
merge commit that shipped the bundle). `outcome` has none of those problems — it
is the irreplaceable, human-authored "what resulted", reconstructable from
nothing else.

So `pr` is dropped from the convention entirely:

- The validator enforces `status: shipped ⇒ outcome` only.
- `pr` is removed from the three `_templates/` frontmatter blocks, from the
  `README.md` frontmatter spec, and from the `format_row` index rendering (the
  listing now shows `(date)`, not `(#pr, date)`). PR traceability lives in git
  history and the `outcome` line.
- The `pr:` line is stripped from every existing bundle and decision
  frontmatter, reverting the now-pointless backfill (the `outcome` backfill
  stays — it was needed regardless).

This supersedes the "backfill all 15" ruling for `pr`; the equivalent work for
`outcome` stands.

Because `outcome` is now the sole enforced lifecycle field, it gets a written
definition in `README.md`'s Frontmatter section (and a guiding placeholder in
the `_templates/`): filled at ship time, one line / ~1–3 sentences (≤ ~300
chars), stating the realized result — what shipped and its effect, deviations
from the plan included — written so a future reader grasps the consequence
without opening the diff, and distinct from the pre-ship intent in `summary`.

### `status` and supersession dropped from change bundles

On `main`, a change bundle is essentially always `shipped` — the in-progress
states (`draft`/`approved`) only exist on an unmerged feature branch, and
"superseded" was derivable from `superseded_by`. So the `draft → shipped` flip
was ceremony with no payoff, and supersession was judged not useful for changes.
Both are removed from change bundles:

- `status`, `supersedes`, and `superseded_by` are removed from the change-bundle
  frontmatter spec, the `_templates/` (design/change/plan), and every existing
  change bundle. A change spec's frontmatter is now `date`, `slug`, `summary`,
  `outcome`; a `plan.md`'s is `date`, `slug`, `spec`.
- The validator requires `outcome` on **every** change spec (no longer gated on
  `status: shipped`); it drops the `status`-validity and supersession checks for
  changes.
- The generated index drops the status grouping: changes render as a flat
  newest-first list. `format_row` is unchanged (the supersession suffixes simply
  never fire for changes).
- **Decisions are unchanged** — `decisions/*.md` keep `status`
  (`accepted`/`superseded`) and `supersedes`/`superseded_by`, where the
  distinction is load-bearing. The validator still checks them.

## Operations

Sibling modern-python repos (e.g. `faststream-outbox`) share the portable
convention. After this lands here, the Quick-path section and the `index.py
--check` additions are copied to each sibling and wired into their `just lint-ci`.
That rollout is per-repo and out of scope for this PR; it is tracked as a
follow-up (a `deferred.md` entry or a decision note, executor's choice).

## Out of scope

Findings 3 (architecture/-promotion heuristic warning), 6 (EARS-style per-task
acceptance criteria), 7 (consolidated finishing-a-change checklist), and 8 (`.NN`
counter helper) are explicitly excluded. They were considered and ruled out for
this change; 6 in particular risks reading as ceremony and needs separate
agreement.

## Testing

- `just check-planning` exits 0 on the cleaned repo and non-zero with a clear,
  itemized message when fed a deliberately broken bundle (validated with a
  throwaway fixture during execution, not committed).
- `just lint-ci` runs `check-planning` as part of the suite and stays green.
- `just index` still renders the listing unchanged (the `--check` addition must
  not alter default/stdout behavior).
- A human read-through confirms the lane decision in the Quick path yields the
  same lane as the existing table on a handful of past changes (no semantic
  drift in the lane rules — only their presentation).

## Risk

- **Validator too strict, flags legitimate historical bundles.** *Mitigation:*
  the bootstrapping step (Design §3) reconciles existing bundles before the gate
  is wired into `lint-ci`; rules are tightened to be precise, not blanket.
  Likelihood medium, impact low (noisy CI, not broken code).
- **De-dup drops a CLAUDE.md detail that was only there.** *Mitigation:* diff
  the removed prose against `planning/README.md` "Conventions" before deleting;
  anything not already covered there stays in CLAUDE.md (this is how the
  release-cutting process is retained). Likelihood low, impact low.
- **Portable drift after copy-out.** The Quick path and `--check` now exist in
  multiple repos and can diverge. *Mitigation:* same as today — the portable
  section is copied, not abstracted; the Operations follow-up notes the sync
  points. Likelihood low, impact low.
