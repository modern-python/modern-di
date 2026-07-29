---
summary: Validation is explicit-only — `validate()` is the sole trigger. The alternative that kept it implicit (splitting the walk into monotone checks at construction and completeness at first use) was implemented, measured, and discarded: its machinery was out of proportion to the guarantee, and the cheap version taxes the resolve hot path for a startup-time concern.
---

# Validation is explicit-only; implicit validation was built and discarded

**Decision:** `container.validate()` is the only thing that walks the graph.
Neither `__init__` nor `open()` nor `add_providers` nor `resolve()` ever
validates, and `Container(validate=...)` is a deprecated no-op. The rule is in
[`validation.md`](../../architecture/validation.md); this records the design
that was tried instead and why it lost.

## Context

3.0 (tagged 2026-07-20) made `open()` mandatory and made it the sole validation
trigger. Both tightenings caused trouble:

- Mandatory `open()` produced six production defects across integrations, all
  one root cause — the root's open hook does not fire in some execution
  contexts, so the first unit of work raises.
- Binding validation to `open()` produced an authoring rule that existed only
  because of that binding: open the root *after* `setup_di`, or a by-type
  dependency on a not-yet-registered connection fails validation.

The question was whether to keep an implicit safety guarantee at all, and if so
how to pay for it.

## Decision & rationale

An earlier revision of this change kept validation implicit by **splitting the
walk in two**:

- **Cycles and inverted scopes, eagerly at construction.** These are *monotone* —
  registering more providers can only ever add such an error, never remove one —
  so they are safe to check before the graph is complete.
- **Completeness (missing dependencies, dangling aliases), held on the shared
  registry and raised at first use**, since it is the only class of error that a
  later `add_providers` can legitimately fix.

It was implemented and it worked. The cost was the machinery it dragged in:

1. A two-flag container lifecycle, so a fresh container could be told from a
   closed one.
2. Validation state parked on `ProvidersRegistry`.
3. A monotone/completeness classification threaded through the graph walk.
4. An `add_providers` rollback path, so a batch that broke the graph could be
   undone.

That is a large, permanent surface for a startup-time property. And the cheap
way to keep the implicit guarantee *without* it — a per-resolve check — taxes
the hot path for a concern that only matters once, at boot.

**Maintainer ruling: make the trigger explicit and predictable instead.**
`validate()` is one call, it reports every wiring bug at once, and nothing about
when it runs has to be inferred. `add_providers` becomes a plain register with
no rollback; the mutation clears `_validated`, so the next explicit `validate()`
re-walks. `ProvidersRegistry` keeps `_validated` purely as a memo of a clean
walk — it gates nothing — and it still short-circuits `resolve_provider`'s
`RecursionError`-to-`CircularDependencyError` guard.

The measurement that came with the ruling: because 3.0 ran a default
`validate=True` graph walk at `open()`, dropping it made construction markedly
cheaper — roughly **2.6 µs against 15.5 µs** for a depth-6 chain
(`Container(...)` + `open()`, default arguments), matching the
`test_g10_validate_deep_chain` guard cost that 3.0's `open()` paid. The resolve
tier was unchanged, as expected: compiled resolvers keep the identical single
`if target.closed:` test per code path, with only the body swapped. The ad hoc
benchmark scenario that produced the construction figure was deleted along with
the split-validation design it existed to measure.

Shipped as 3.1.0. Every 3.0 pattern keeps working; no integration needed a code
change. `Container(validate=...)` stays accepted-and-ignored (with
`ValidateArgumentWarning`) until 4.0 specifically because 3.0 callers pass
`validate=False` widely, including this repo's own benchmark guards.

**The accepted cost:** the default safety posture drops silently. A broken graph
previously raised at `open()`; now it surfaces from an explicit `validate()`, or
at resolve time as `ArgumentResolutionError`. Nothing that worked breaks, but a
user who believed the default protected them loses that. The deprecation warning
plus the release notes and integration docs carry the replacement idiom.

## Revisit trigger

Reports of graphs reaching production broken in a way an implicit walk would
have caught at boot — i.e. evidence that opt-in `validate()` is under-adopted in
practice. Re-open with the adoption evidence, not with a new mechanism: the
split-validation design is settled, and any replacement must avoid both the
four-part machinery above and a per-resolve check.
