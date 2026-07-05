---
status: accepted
summary: Rejected yield-based generator creators for 3.0; CacheSettings(finalizer=) stays the single teardown channel.
supersedes: null
superseded_by: null
---

# No generator creators in core Factory

**Decision:** `Factory` will not auto-detect generator creators and turn post-`yield` code into a
finalizer; `CacheSettings(finalizer=)` remains the only teardown spelling in core.

## Context

The 2026-07-05 3.0 UX research (candidate API-2) found every Python peer — dishka, wireup, svcs,
FastAPI yield-dependencies, that-depends `Resource` — spells teardown as code after `yield` in the
factory itself, making it the strongest muscle-memory delta for migrants. The proposal ranked #4 in
the shortlist and would have been breaking: `Factory(creator=generator_fn)` is legal today and
resolves to the raw generator object, so auto-detection changes existing behavior. It also carried
open design complexity: per-instance finalizer records for non-cached factories (or a `cache=`
requirement), declaration-time rejection of async generators, and `bound_type` extraction from
`Iterator[T]`.

## Decision & rationale

Rejected for core: the additions are complex relative to the ergonomic win, and the capability is
achievable without core changes — a `Factory` subclass (in userland or a sibling package) can wrap a
generator creator and register the continuation via the existing `CacheSettings(finalizer=)`
channel. Keeping one explicit teardown spelling also preserves the property that async finalizers
work under sync resolution, which the generator form cannot express.

## Revisit trigger

Recurring user requests for yield-based teardown, or a community-built generator-factory subclass
demonstrating both the demand and a settled design.
