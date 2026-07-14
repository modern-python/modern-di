---
status: accepted
summary: Making SignatureItem an opaque resolved parameter (a 2026-07-13 review candidate) is superseded — the graph-traversal unification already extracted its two behaviours as wiring.py functions.
supersedes: null
superseded_by: null
---

# SignatureItem opacity is superseded by the wiring extraction

**Decision:** Do not pursue "make `SignatureItem` an opaque resolved
parameter" (Candidate 3 from the 2026-07-13 architecture review). Its
substance already shipped in the graph-traversal unification
([2026-07-12.01-dependency-graph-module](../changes/2026-07-12.01-dependency-graph-module.md),
PR #308), which placed the behaviour better than the candidate's sketch.

## Context

The review flagged `SignatureItem` (`types_parser.py`) as a shallow record
whose five raw fields (`arg_type`, `args`, `is_nullable`, `default`,
`raw_annotation`) were decoded independently at ~5 sites, and proposed
absorbing that behind two operations — `match_provider(reg)` ("which provider
backs this?") and `disposition()` ("what if absent?") — ideally as methods on
`SignatureItem`, so callers never touch the raw fields.

## Decision & rationale

The core leak — the old wiring loop reading raw fields to pick providers and
handle absence — is gone. `modern_di/wiring.py` now owns exactly those two
operations as free functions:

- `find_dep_provider(registry, owner, item)` = `match_provider` — prefers
  `arg_type`, falls back to union `args`.
- `absent_disposition(item)` = `disposition` — default → OMIT, nullable →
  NULL, else UNWIRABLE.

`WiringPlan.build` (the former leaky loop) calls these two and touches no raw
field. The candidate's proposal is realized.

The free-function placement in `wiring.py` is **deliberately better** than the
candidate's "methods on `SignatureItem`" idea: `SignatureItem` stays a pure
data record in `types_parser.py` and does not import `ProvidersRegistry` /
`AbstractProvider`. Methods-on-`SignatureItem` would invert that layering
(the parse-tree type depending on the resolution machinery).

The residual raw-field reads that remain (all in `providers/factory.py`) are a
thinner, different set — the parameterized-generic construction guard
(`raw_annotation` + `default`), the error builder (`arg_type` + `args`), and
deriving `bound_type` from the return sig's `arg_type`. None is duplication,
none collapses into `match_provider`/`disposition`, and each is a single
legitimate read. Forcing a further "opacity" refactor here would be churn
without a genuine deepening.

## Revisit trigger

A *new* duplicated raw-field decode idiom appears across two or more sites
(the repeated-idiom smell the review originally caught), or `types_parser.py`
gains logic that would genuinely benefit from behaviour living on the record
without inverting the `types_parser` → `wiring` layering.
