---
summary: ProvidersRegistry.resolver_for compiles outside the lock and stores the memo after, so a registration landing in that window clears a memo the resolver has not entered yet and the stale resolver is then written in and never dropped — verifiable by reading, out of contract today, and a hard blocker on alias source binding.
---

# Resolver-memo publication race in `ProvidersRegistry.resolver_for`

`resolver_for` compiles a resolver **outside** `self._lock` and writes it to the
memo **after** compiling:

```python
building.add(pid)
try:
    resolver = compile_resolver(provider, self)  # outside _lock
finally:
    building.discard(pid)
self._resolvers[pid] = resolver  # store after, also outside _lock
```

`register()` and `add_providers()` hold `_lock` and call `_invalidate()`, which
does `self._resolvers.clear()`. A compile that began before an `_invalidate()`
therefore stores its result *after* the clear. The stored resolver was compiled
against the pre-registration registry — its dependency resolvers, its wiring plan
and its captured scope all predate the new provider — and nothing will ever drop
it, because the invalidation it needed has already happened.

## Why it is open

**What is confirmed:** the code shape, by reading. `_invalidate()`'s own
docstring says it is "called under `self._lock` by every mutation", and the memo
write in `resolver_for` is not. The ordering hazard is not in dispute.

**What is not confirmed:** that it is reachable in practice. An adversarial
reviewer reported 375/400 trials producing a permanently-stale optional `Factory`
dependency under plain threads. **That figure was not reproduced.** Two direct
attempts here found 0/200 and 0/150 — the first with a small graph, where the
window between `compile_resolver` returning and the memo store is a couple of
bytecodes; the second with a deliberately widened window, which was itself
invalid (the constructed graph raised `ArgumentResolutionError` and never
exercised the path). Treat the frequency as unverified and the shape as real.

**Why it is out of contract today.** `add_providers`'s docstring calls
registration "a startup-time operation: concurrent calls on the same root are not
coordinated beyond the registry's internal lock", and
[`architecture/concurrency.md`](../../architecture/concurrency.md) defines the
configure phase as single-threaded. Registering concurrently with resolution is
therefore unsupported, which is what keeps this latent rather than live. It is
recorded because "unsupported" and "silently wrong" are different things, and
this fails silently and permanently rather than raising.

**Why it matters beyond itself.** It is a hard blocker on
[`2026-08-01-alias-source-binding.md`](2026-08-01-alias-source-binding.md): the
alias candidate's licensing invariant is that a source registered after compile
is picked up via `_invalidate()`, and this window makes that false. Today's alias
is accidentally immune only because it re-looks-up its source on every resolve.

**The proposed fix is small**: a generation counter on the registry, bumped by
`_invalidate()`, read before `compile_resolver`, and — under `_lock` — used to
store the memo only if the generation is unchanged. It costs one integer compare
on the compile path, which is cold, and nothing on the warm path.

## Revisit trigger

Any of: a decision to support registration concurrent with resolution (which
would make this live rather than latent); picking up alias source binding, which
cannot proceed without it; or a reproduction of the stale-resolver failure that
survives scrutiny, which would reclassify this as a bug to fix now rather than a
hazard to record. Fixing it on its own merits is also reasonable — the fix is
cheap and the failure mode is silent.
