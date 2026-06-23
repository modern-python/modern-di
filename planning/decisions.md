# Decisions

Design decisions deliberately taken — especially options **considered and
rejected** — kept so future work (and architecture reviews) don't re-litigate
them. The `architecture/` truth home says *what the system does now*; this
records *why it isn't done differently*. Each entry stands alone, readable cold.

Append newest at the top. If this file grows past a handful of entries, split it
into `decisions/<YYYY-MM-DD>-<slug>.md` the way `audits/` and `retros/` work.

## Keep sync and async `close` paths separate — 2026-06-23 architecture review (candidate 4)

**Decision:** Leave `close_sync` / `close_async` as explicit pairs at all three
layers (`Container`, `CacheRegistry`, `CacheItem`). Do **not** unify them into
single parametrized methods.

**Context:** A review candidate flagged "six near-identical `close_*` methods" as
a shallow seam ripe for deduplication. Investigation showed the surface
similarity is misleading — only the `Container` pair is near-identical (one line
differs: `cache_registry.close_sync()` vs `await …close_async()`). The other two
layers diverge for intrinsic reasons:

- `CacheItem` — async `await`s the finalizer's result; sync **cannot await**, so
  it detects an async finalizer (the `is_async_finalizer` flag or an awaitable
  result), `.close()`s the coroutine to suppress the "never awaited" warning, and
  raises `AsyncFinalizerInSyncCloseError`.
- `CacheRegistry` — async clears `_creation_order` entirely; sync **preserves**
  the items that raised `AsyncFinalizerInSyncCloseError` in `_creation_order` so a
  later `close_async()` can finish them.

The genuinely-shared code is tiny (a ~4-line wrapper, a one-line guard, an
iterate-collect-raise skeleton). The *different* code is exactly the
sync-can't-await and preserve-for-later-async behaviors — a unified method would
have to re-introduce them as conditional branches, **adding** complexity rather
than concentrating it (the deletion test fails).

**Rejected alternative:** one `_close(*, is_async)` (or callback-driven)
method per layer. Rejected because the fork is behavioral, not incidental, and
because the divergent branches carry hard-won correctness: every historical
finalizer fix lives there — B-7 LIFO teardown (`3f9a64b`), B-8 await/reject
sync-finalizer handling (`19e7c72`), async-finalizer rejection (`faf2108`),
finalizer-dedup on `clear_cache=False` (`8ce0ff4`). All shipped in 2.15.0; the
area has been stable since. Unifying would risk regressing precisely those cases
for no locality, leverage, or testability gain.

**Revisit trigger:** if finalizer/close bugs start recurring (the signal that the
explicit pairs are *causing* errors rather than encoding them), or if a third
distinct sync/async-spanning consumer appears that would share real logic. Until
then the layering is honest — each `close` level adds one real concern — and
stays as is.
