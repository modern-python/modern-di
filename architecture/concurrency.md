# Concurrency and free-threaded (PEP 703) safety

modern-di is safe to resolve from multiple threads, and supported on free-threaded
CPython (PEP 703, the `3.14t` build) at level **`2 - Beta`**: production-ready
and tested under real multithreading, with the caveats below documented. This
page is the standing contract.

## The lifecycle

A container has three phases, and thread-safety is defined per phase — build → resolve → dispose shape:

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
   single-threaded edge, after all concurrent resolution has finished —
   **closing or reopening a container while other threads still resolve from it
   is not supported.**

Reuse-after-close is a race the concurrent resolve phase does handle, distinct
from the unsupported race above: once a container has settled into the closed
state at a single-threaded edge, nothing prevents several threads from then
independently calling `resolve` on that (now-closed) container at once — each
unaware the others are doing the same. A container is open from construction
(see [containers.md](containers.md#optional-open-lifecycle)), so this is the
only path back to `closed = True` in the first place. `resolve` and
`resolve_provider` each call `_prepare()` whenever `self.closed` is `True`; `_prepare()` warns and sets
`closed = False`, unlocked. The reopen needs no lock because it is idempotent —
N threads racing a closed container all write the same `False`, and they go on
to share one singleton via the cache lock below. What is *not* serialized is the
warning: each racing thread may emit its own `ContainerClosedWarning`. The
contract is **at least one** warning per reuse-after-close, not exactly one.
Under the default warning filters Python's own per-location registry collapses
the duplicates anyway; `simplefilter("always")` reveals them. `open()` is the
same unlocked idempotent write, minus the warning.

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
  of `(provider, registry contents)`, cleared on mutation. Two threads racing to build
  the same entry produce identical objects; the worst
  case is one duplicated build, never a wrong result. Clearing on mutation is sound because
  mutation is a single-threaded configure-phase operation (see [The lifecycle](#the-lifecycle)
  above). **Publication is generation-checked**, which restores the rebuild-stale safety
  net a plain version stamp used to provide: both `resolver_for` and `plan_for` read
  `_generation` before building, build outside the lock, and then publish under it *only if*
  the generation is unchanged. Without that check a build begun before an `_invalidate()`
  would store its result after the clear, stranding an entry compiled against a registry
  that no longer exists — permanently, since the invalidation meant to drop it has already
  happened. A build that loses the race is returned to its caller and simply not memoized. The cycle-guard `_building`
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
not **Stable**.

## Caveats

- **Configure and close at single-threaded edges** (see [The lifecycle](#the-lifecycle)).
  `override` / `reset_override` and `set_context` mutate shared state without a
  lock; racing them against live `resolve()` is inherently unordered (it always
  was, GIL or not). `close` / `open` are the same: tear a container down only
  after concurrent resolution has stopped.
- **Thread-safe, but resolve throughput does not scale across cores.** Measured
  (guard benchmarks G14/G15): concurrent resolution is correct and per-op latency
  is competitive, but adding threads does not raise throughput on a free-threaded
  build — it tracks the GIL. The cause is CPython's atomic reference counting of
  the objects every resolve shares (the returned singleton value, the provider
  objects, the compiled-resolver closures and their captured cells), not the
  per-container lock and not anything modern-di can remove without immortalizing
  those objects (no public CPython API). It is a CPython-level limitation that its
  own expanding deferred reference counting (PEP 703) will lift for free as it
  reaches ordinary instances. See the [free-threaded scaling diagnosis](../planning/deferred/2026-07-19-free-threaded-throughput.md).
