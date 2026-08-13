---
summary: Declined inlining the ContextProvider resolver into its compiled closure — it freezes cp.scope against a live mutation, buys 0 ns on the factory-dependency path that actually matters, and was dominated by a one-line find_context change that is faster on both paths.
---

# Declined: inlining the ContextProvider resolver into its closure

**Decision:** `_compile_context_provider` keeps delegating to the bound
`ContextProvider.resolve`. Its body is not inlined into the compiled closure.

## Context

`_compile_context_provider` is the one Factory-style resolver that does not
inline its own body: it delegates to `cp.resolve`, which calls
`fetch_context_value`, which calls `find_container` (always — with no same-scope
int-compare fast path, unlike every Factory closure) and then `find_context`.
An automated inventory measured a direct `ContextProvider` resolve at ~233 ns
against a plain factory's ~196 ns, with 8 Python calls against 4, and proposed
capturing `cp.context_type` and `cp.scope` at compile time to remove four frames.

## Decision & rationale

Three independent reasons, any one sufficient.

**It freezes `cp.scope` against a mutation that is live at the time.** Capturing
the scope in the closure is only sound if the scope cannot change after compile.
It could: `AbstractProvider._stamp_group_scope` mutated `provider.scope` and
touched no registry, so `_invalidate()` never fired and the memoized resolver was
never dropped. A `Group` subclass declared after first resolve could restamp a
shared `ContextProvider` from APP to REQUEST; today's delegating resolver raises
`ScopeNotInitializedError`, and the inlined one would return a silently stale
value. That hazard has since been closed at its source — documented at the time
in `architecture/providers.md` (since removed) and enforced by
`ProviderScopeFrozenError` — but it was closed by *freezing the scope at
registration*, not by making the capture safe in general, and it was found while
refuting this candidate rather than before proposing it.

**It buys nothing where it matters.** The measured win is on a *direct*
`resolve_provider(context_provider)` call. On the factory-dependency path — a
`Factory` with a context kwarg, which is what every integration actually does —
the gain measured **0 ns**, because that path goes through
`Factory._resolve_context_value`, not through the compiled ContextProvider
resolver at all.

**It was dominated.** A one-line change to `ContextRegistry.find_context`
(dropping a `typing.cast` and a dead `None` check) was faster on *both* paths for
a net **-1 line**, against this candidate's +27 lines and 0 deleted. That shipped
instead; see the `find_context` PR body for its numbers and for why the
`.get(key, UNSET)` variant was rejected in turn.

## Revisit trigger

A profile from a real integration shows direct `ContextProvider` resolution — not
context *kwargs* on a factory — as a measurable cost, **and** the scope capture
can be licensed by something stronger than the current freeze-at-registration
rule. Absent the first, this optimises a path nobody takes.
