# Keep sync and async `close` paths separate

**Decision:** `close_sync` / `close_async` stay explicit pairs at all three layers (`Container`,
`CacheRegistry`, `CacheItem`); they are not unified into single parametrized methods.

"Six near-identical `close_*` methods" is a surface reading. Only the `Container` pair is
near-identical (one line differs). The other two diverge intrinsically:

- **`CacheItem`** — async awaits the finalizer's result; sync **cannot await**, so it detects an
  async finalizer, `.close()`s the coroutine to suppress the never-awaited warning, and raises
  `AsyncFinalizerInSyncCloseError`.
- **`CacheRegistry`** — async clears `_creation_order` entirely; sync **preserves** the items that
  raised `AsyncFinalizerInSyncCloseError` so a later `close_async()` can finish them.

The genuinely shared code is a ~4-line wrapper, a one-line guard, and an iterate-collect-raise
skeleton; unifying would re-introduce the sync-can't-await and preserve-for-later behaviours as
conditional branches, **adding** complexity rather than concentrating it. Those branches also carry
every historical finalizer fix — LIFO teardown (`3f9a64b`), await/reject sync finalizers
(`19e7c72`), async-finalizer rejection (`faf2108`), `clear_cache` finalizer-dedup (`8ce0ff4`), all
shipped in 2.15.0 — and the area has been stable since.

**Revisit trigger:** finalizer/close bugs start recurring (the signal that the explicit pairs are
*causing* errors rather than encoding them), or a third distinct sync/async-spanning consumer
appears that would share real logic.
