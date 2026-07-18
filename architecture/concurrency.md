# Concurrency and free-threaded (PEP 703) safety

modern-di is safe to resolve from multiple threads, and supported on free-threaded
CPython (PEP 703, the `3.14t` build) at trove level **`2 - Beta`**: production-ready
and tested under real multithreading, with the caveats below documented. The
[2026-07-17 research report](../planning/audits/2026-07-17-nogil-support-research-report.md)
is the full analysis; this page is the standing contract.

## The lifecycle

A container has three phases, and thread-safety is defined per phase — the same
build → resolve → dispose shape every comparable DI framework assumes (the
[2026-07-18 concurrency-contract research](../planning/audits/2026-07-18-di-concurrency-contract-report.md)
found no framework that supports tearing a container down while other threads
resolve from it):

1. **Configure — single-threaded (startup).** Registering providers
   (`add_providers`, group construction) mutates the registry under its own lock,
   but the resolve path reads the registry without taking that lock; `override` /
   `reset_override` and `set_context` mutate shared state with no lock at all.
   Either way, racing these against live `resolve()` is unsafe — do them on one
   thread before concurrent resolution begins.
2. **Resolve — concurrent (the hot phase).** `resolve` / `resolve_provider` /
   `resolve_dependency` and `build_child_container` are safe to call from many
   threads at once. Singleton creation is locked and double-checked (see below),
   so a cached value is built exactly once and shared.
3. **Close — single-threaded (shutdown).** `close_sync` / `close_async` run
   finalizers and reset caches/overrides; `open` reopens a closed container so it
   can resolve and build children again. Close (or reopen) a container at a
   single-threaded edge, after concurrent resolution has quiesced — **closing or
   reopening a container while other threads still resolve from it is not
   supported.**

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

- **Configure and close at single-threaded edges** (see [The lifecycle](#the-lifecycle)).
  `override` / `reset_override` and `set_context` mutate shared state without a
  lock; racing them against live `resolve()` is inherently unordered (it always
  was, GIL or not). `close` / `open` are the same: tear a container down only
  after concurrent resolution has stopped.
- **Performance, not correctness, is the open question.** Whether the
  per-container lock contends under heavy parallel first-resolution is unmeasured
  and out of scope for the Beta claim (report §7).
