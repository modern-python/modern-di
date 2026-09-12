# Drop the warm-singleton resolver memo-swap

**Decision:** the resolver memo is never self-modified after a singleton is built. The mechanism
(swap a cached provider's stored resolver for a bare `return value`, wireup's technique) was built,
measured and reverted.

**Why:** it is sound only at `APP` scope, where one registry maps to one container and one value;
deeper scopes cache per child. Measured at ~1.6x on the warm hit (guard G2 584 → 375 ns), enough to
pass dishka but short of the pre-committed gate of at least halving, because the dispatch upstream
of the closure body (the entry-point lookups) was not touched by the swap. A bounded win did not
buy a permanent cross-cutting invalidation invariant spanning `override()`, `close()` and
`add_providers()`. Two things were kept: the free-threaded stress test it produced, and the
invalidate-on-mutation simplification it pointed at. The template resolver
([ADR-0030](0030-exec-template-resolver.md)) later removed the override guard from the warm hit;
the remaining gap to a C-level or lock-free slot read is a floor pure Python does not reach.
