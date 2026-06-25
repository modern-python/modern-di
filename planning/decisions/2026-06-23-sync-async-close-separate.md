---
status: accepted
date: 2026-06-23
slug: sync-async-close-separate
summary: Keep sync/async close paths separate — the divergence is intrinsic, not duplication.
supersedes: null
superseded_by: null
---

# Keep sync and async `close` paths separate

**Decision:** Leave `close_sync` / `close_async` as explicit pairs at all three
layers (`Container`, `CacheRegistry`, `CacheItem`); do not unify them into single
parametrized methods.

## Context

Architecture-review candidate #4 flagged "six near-identical `close_*` methods" as
a shallow seam ripe for deduplication. Investigation found the surface similarity
misleading — only the `Container` pair is near-identical (one line differs:
`cache_registry.close_sync()` vs `await …close_async()`). The other two layers
diverge intrinsically:

- **`CacheItem`** — async `await`s the finalizer's result; sync **cannot await**,
  so it detects an async finalizer (the `is_async_finalizer` flag or an awaitable
  result), `.close()`s the coroutine to suppress the "never awaited" warning, and
  raises `AsyncFinalizerInSyncCloseError`.
- **`CacheRegistry`** — async clears `_creation_order` entirely; sync
  **preserves** the items that raised `AsyncFinalizerInSyncCloseError` in
  `_creation_order` so a later `close_async()` can finish them.

The genuinely-shared code is tiny (a ~4-line wrapper, a one-line guard, an
iterate-collect-raise skeleton). The *different* code is exactly the
sync-can't-await and preserve-for-later behaviors — a unified method would
re-introduce them as conditional branches, **adding** complexity rather than
concentrating it (the deletion test fails).

## Decision & rationale

Keep the explicit pairs. The divergent branches carry every historical finalizer
fix: B-7 LIFO teardown (`3f9a64b`), B-8 await/reject sync finalizers (`19e7c72`),
async-finalizer rejection (`faf2108`), `clear_cache` finalizer-dedup (`8ce0ff4`)
— all shipped in 2.15.0, and the area has been stable since. Unifying would risk
regressing precisely those cases for no locality, leverage, or testability gain.
The layering is honest: each `close` level adds one real concern.

## Revisit trigger

If finalizer/close bugs start recurring (the signal that the explicit pairs are
*causing* errors rather than encoding them), or if a third distinct
sync/async-spanning consumer appears that would share real logic.
