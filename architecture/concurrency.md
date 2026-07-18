# Concurrency and free-threaded (PEP 703) safety

modern-di is safe to resolve from multiple threads, and supported on free-threaded
CPython (PEP 703, the `3.14t` build) at trove level **`2 - Beta`**: production-ready
and tested under real multithreading, with the caveats below documented. The
[2026-07-17 research report](../planning/audits/2026-07-17-nogil-support-research-report.md)
is the full analysis; this page is the standing contract.

## The model

- **Singleton creation is the only locked path.** A cached `Factory` builds its
  value under the resolving container's `threading.RLock`, double-checked: the
  dependency graph resolves *outside* the lock, then creation and the cache store
  run *inside* it behind a second cache-populated check, so at most one caller ever
  runs the creator (`CacheItem.get_or_create`). Concurrent first-resolvers of the
  same singleton share **one** `CacheItem` because `CacheRegistry.fetch_cache_item`
  publishes it with `dict.setdefault` — a single atomic operation. Containers built
  with `use_lock=False` opt out of the lock and are single-thread-only.
- **Registry memoization is lock-free and idempotent.** The compiled resolver, the
  wiring plan, and their registry caches (`_resolvers`, `_plans`) are pure functions
  of `(provider, registry version)`. Two threads racing to build the same entry
  produce identical objects and store the same `(version, object)` tuple; the worst
  case is one duplicated build, never a wrong result. The cycle-guard `_building`
  set is **thread-local**: it tracks which providers are being compiled on *this*
  call stack, so a genuine same-thread `A -> B -> A` cycle is still caught by the
  back-edge thunk, while a concurrent first-resolve of the same provider on another
  thread simply compiles it independently (an idempotent duplicate) rather than
  being misread as a cycle. (A shared `_building` set was a real bug fixed in this
  change — it recursed to `RecursionError` on acyclic graphs under concurrent
  first-resolution.) Registry *mutation* (`register` / `add_providers` / removal)
  is guarded by the registry's own lock.

## Why this is sound without the GIL

Free-threaded CPython makes single built-in-container operations (`dict.setdefault`,
`dict[k] = v`, `dict.get`, `list.append`) internally atomic — one such operation
cannot corrupt the structure. modern-di never relies on a *compound* check-then-act
over shared state being atomic: every such sequence above is either idempotent
(rebuild-if-stale) or already under the container lock. The one reliance CPython
does not *formally* guarantee is object-publication ordering — that a reader
observing a stored reference sees the object's fully-initialized fields — because
CPython publishes no memory model. In the current implementation, publication
through a container's internal critical section provides that ordering; that gap
between "implementation behavior" and "spec guarantee" is why the claim is **Beta**,
not **Stable**. See the report for the full argument.

## Caveats

- **Apply overrides before concurrent resolution.** `override()` / `reset_override()`
  mutate a shared registry without a lock; racing them against live `resolve()` calls
  is inherently unordered (it always was, GIL or not). Set overrides during
  single-threaded setup, then resolve concurrently.
- **Seed context before concurrent resolution too.** `set_context` writes a shared
  dict; populate a container's context before resolving from it on many threads.
- **Performance, not correctness, is the open question.** Whether the per-container
  lock contends under heavy parallel first-resolution is unmeasured and out of scope
  for the Beta claim (report §7).
