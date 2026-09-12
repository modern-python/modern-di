# Keep sync and async `close` paths separate

**Decision:** `close_sync` / `close_async` stay explicit pairs on `Container`, `CacheRegistry` and
`CacheItem`; they are not unified into one parametrized method.

**Why:** only the `Container` pair is near-identical. `CacheItem.close_sync` cannot await, so it
detects an async finalizer, closes the coroutine to suppress the never-awaited warning, and raises
`AsyncFinalizerInSyncCloseError`; `CacheRegistry.close_sync` preserves the items that raised it so
a later `close_async` can finish them, where the async path clears the creation order outright. A
unified method would carry both behaviours as conditional branches, adding complexity rather than
concentrating it. The area has been stable since the finalizer fixes shipped in 2.15.0.
