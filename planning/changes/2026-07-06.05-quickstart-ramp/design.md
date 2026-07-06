---
summary: Progressive-disclosure quickstart (DOC-2) — first success with Group + Factory + resolve, cache/finalizer as lesson two, scopes as lesson three.
---

# Design: Progressive-disclosure quickstart

## Summary

Implements shortlist ruling DOC-2 (2026-07-05 UX research). `docs/index.md`
front-loads two scopes, `cache=True`, and `build_child_container` in the very
first example — 5-6 concepts before first resolve, versus 2 for svcs/FastAPI
and 4 for wireup (verified in the research). Nothing beyond Group + Factory +
`resolve` is needed for an honest first success (Factory defaults to
`scope=Scope.APP`). Restructure the ramp; no API changes; precedent: FastAPI's
dependencies tutorial escalation, Angular's essentials/deep-guide split.

## Design

Target shape for `docs/index.md` (keep the existing hero/badges/install and
the "Where to next" links, which now include the anti-patterns page):

1. **Step A — first success (~10 lines):** one `Group`, one plain `Factory`,
   `Container(groups=[...], validate=True)` (explicit `validate=` is the
   house spelling since the 2.24.0 sweep), `container.resolve(T)`. No scopes,
   no caching, no child containers mentioned yet.
2. **Step B — create once, reuse (singleton):** add `cache=True` and a
   finalizer; make identity observable (MEDI GUID-style: print/compare
   `id(...)` across two resolves, then show the finalizer running on close
   via the `with` form).
3. **Step C — request scope:** introduce `Scope.REQUEST`,
   `build_child_container(scope=..., context={...})`, and one context-typed
   dependency — the smallest honest request-boundary example.
4. Close with "Where to next" (Providers pages own the deep material).

Rules:
- Each step builds on the previous snippet with minimal diff noise; a
  first-time reader must never meet a concept before the step that teaches it.
- Content currently on index.md that exists nowhere else must be relocated
  (to the owning Providers/Recipes page), not deleted; content duplicated
  elsewhere may be dropped from index.md.
- Every snippet runnable as written (spot-run each step).

## Non-goals

- No changes to other pages beyond relocation targets; no nav changes; no
  API or code changes.

## Testing

Spot-run all three step snippets as scripts; `just docs-build` (strict);
`just lint-ci`. Review reads the page as a first-time user (the docs-ux
audit's onboarding lens) and checks the concept-before-use rule.

## Risk

Losing content in the restructure (medium/low): mitigated by the
relocate-don't-delete rule and a reviewer diff pass over removed blocks.
