# Decisions

Design decisions taken — especially options **considered and rejected** — so
future work doesn't re-litigate them. Keep each entry to a few lines: the call,
why, and a revisit trigger; link a PR/commit for the full reasoning. If an entry
truly needs more room, give it its own file under `decisions/<YYYY-MM-DD>-<slug>.md`.
Newest first.

## 2026-06-23 — Keep sync/async `close` paths separate (review candidate 4)

Won't unify the six `close_sync`/`close_async` methods (`Container` /
`CacheRegistry` / `CacheItem`). Only the `Container` pair is near-identical;
the other two diverge intrinsically — sync can't `await`, so it rejects async
finalizers and preserves them for a later `close_async`. Shared code is tiny;
the divergent branches hold every historical finalizer fix (B-7/B-8/dedup, all
2.15.0, stable since), so unifying adds branching and risks regressing them.
**Revisit if** finalizer bugs recur, or a third sync/async-spanning consumer
appears. Full investigation: PR #229.
