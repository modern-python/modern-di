---
status: accepted
summary: Accept an except-body-only helper for the creator-call TypeError rule — it dodges the frame cost that made the drift-lock bundle reject a shared helper, because the moved code runs only on the raise path.
supersedes: null
superseded_by: null
---

# Extract the creator-call error rule via an except-body-only helper

**Decision:** Centralize the creator-call `TypeError` rule in one
`CreatorCallError.from_type_error` classmethod, called from inside each site's
`except TypeError` block. This supersedes the "no shared helper" non-goal
recorded in
[2026-07-17.02-creator-call-error-drift-lock](../changes/2026-07-17.02-creator-call-error-drift-lock.md).

## Context

The drift-lock bundle (`changes/2026-07-17.02`) faced the same four-copy
duplication of the rule "a binding `TypeError` becomes `CreatorCallError` with a
prepended step; a `TypeError` from inside the creator body propagates unchanged."
It explicitly rejected deduping: *"Do not extract a shared helper — that
reintroduces the frame the inlining removed,"* and locked the copies with a
cross-path equivalence test instead.

That rejection weighed one helper shape: a helper wrapping the whole
`creator(...)` call, which adds a Python frame on **every** resolve — the success
path the [single-path compiled resolver](../changes/2026-07-16.02-single-path-compiled-resolver.md)
inlining exists to keep frame-free.

The option it did not weigh: extract only the `except`-body — the `tb_next`
discriminate, the `CreatorCallError` construction, and the `prepend_step` — while
leaving `try: return creator(...)` at each site. That code runs only when the
creator call raises `TypeError`, i.e. on the already-failing raise path, never on
success.

## Decision & rationale

Chose the except-body helper. The drift-lock bundle's objection is real but
scoped to whole-call wrapping; it does not bind the except-body form. Under this
form:

- The success (hot) path stays `return creator(*args)` byte-for-byte — no frame
  is restored. A `--benchmark-compare-fail=mean:5%` resolve-bench gate confirms
  it empirically before ship.
- The rule gets one home (locality); changing it is one edit, not four.
- The equivalence test that existed only to police the copies is retired — one
  source cannot drift from itself.
- Traceback fidelity is preserved: the return-or-`None` contract keeps the bare
  `raise` at each site, so a creator-body `TypeError` propagates with its
  traceback unchanged.

The narrower frame concern the drift-lock bundle protected is honored, not
overridden — the reversal applies precisely because the except-body form
sidesteps it.

## Revisit trigger

The resolve hot path regresses after this lands (meaning the success path was not
as frame-free as argued), **or** a future change needs the creator-call rule to
differ per site again (making a single shared rule wrong) — either reopens the
single-home decision.
