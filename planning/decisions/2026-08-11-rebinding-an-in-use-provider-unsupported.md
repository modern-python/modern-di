---
summary: Changing a ContextProvider's `scope` or `context_type` after a consumer's resolver has compiled against it is unsupported and only partially enforced — construct a second provider instead.
---

# Rebinding an in-use `ContextProvider` is unsupported

**Decision:** Mutating a `ContextProvider`'s `scope` or `context_type` after something has already
resolved through it — compiling a consumer's resolver closure against it — is not a supported
operation. This is a contract, not a mechanism: enforcement is inconsistent by design, not a gap to
close. Construct a second provider instead of rebinding an existing one.

## Context

A `ContextProvider`'s `scope` and `context_type` are read once, when a consumer's resolver is
compiled, and folded directly into that closure. Nothing about either attribute touches a registry,
so nothing invalidates the memo when they change afterward. Changing either attribute post hoc applies
only to resolvers compiled *later* — silently, with no error and no signal that older, already-compiled
consumers are now working from a stale value.

Whether that silent staleness is caught at all depends on which attribute and which route:

- `scope` on a **registered** provider is enforced against group stamping by
  `ProviderScopeFrozenError` — attempting to re-stamp a registered provider's scope raises.
- `scope` on a provider that was never registered — one passed only inline, e.g.
  `Factory(creator, kwargs={"x": cp})` — is **not** enforced. `_registered` stays `False` for such a
  provider, so a later `Group` can stamp its scope without error, silently.
- `context_type` is **not enforced on either route**. There is no equivalent guard for it at all.

So three of the four (attribute, route) combinations either enforce nothing or enforce it
inconsistently with the fourth. That asymmetry was deliberate at the time each piece was built —
`ProviderScopeFrozenError` exists to protect group stamping, not attribute mutation in general — but
it means a caller cannot rely on an exception to catch a rebind.

## Decision & rationale

**Declare the whole surface unsupported rather than patch the three unguarded corners.** Closing all
three gaps would mean tracking "has anything resolved through this provider yet" as new mutable state
on every `ContextProvider`, checked on every attribute write, to protect an operation (rebinding scope
or context type on a live provider) that has no legitimate use case distinguishable from a bug: nobody
needs a provider that changes identity mid-flight, and existing resolved values are not migrated with
it in any case.

The one exception path — a `ContextProvider` passed via `kwargs={...}` for a parameter with no parsed
`SignatureItem` (a `**kwargs` creator, or `skip_creator_parsing=True`) — still goes through
direct-resolve semantics and raises `ContextValueNotSetError` when unset, which is unrelated to this
decision; it's about absence, not about rebinding an already-resolved provider.

**Accepted cost:** a caller who does rebind a never-registered provider's `scope`, or either route's
`context_type`, gets no error — just resolvers that silently disagree about what type or scope the
provider has, split along whichever side of the compile boundary they landed on. This is disclosed
rather than fixed because fixing it costs a mutable per-provider tracking flag for a mistake that has
no other repro path in the test suite or issue history.

## Revisit trigger

A real bug report traces back to one of the three unguarded corners — most plausibly the
never-registered-provider `scope` gap, since that one silently *succeeds* where the registered case
raises. At that point the fix is a symmetric guard (extend `ProviderScopeFrozenError`-style enforcement
to the unregistered route, and add an equivalent for `context_type`) rather than continuing to disclaim
it.
