---
summary: Concurrent resolve is thread-safe but does not scale with threads on a free-threaded build — diagnosed as CPython atomic refcount contention on shared hot-path objects, not the lock, and not liftable from this side; the fix is CPython's.
---

# Free-threaded resolve throughput does not scale

On a free-threaded build (PEP 703), modern-di's concurrent resolve is thread-**safe**
but its throughput does not rise with thread count. Cached-hit batch time is
flat-to-worse as threads increase and matches the GIL build, while a pure-compute
control on the same harness scales ~3.5x at 4 threads.

## Why it is open

A thread-isolation sweep (fixed total work split across 4 threads on 3.14t, GIL
confirmed off; speedup = t1/t4, ceiling ~3.8x from a pure-compute control) pinned
exactly what serializes:

| case | what is shared across threads | 4-thread speedup |
|---|---|---|
| pure compute | nothing | 3.8x (ceiling) |
| fully thread-local (distinct provider + container + value) | module globals only | 2.17x |
| distinct container per thread | + the **provider** object | 0.92x |
| distinct value, shared container | + provider + machinery | 0.84x |
| same singleton (the G14 case) | + the **returned value** | 0.64x |
| raw `dict.get` → one shared value | just the value's refcount | 0.28x |

The read path is bounded by atomic reference counting on the objects every
resolve shares: most sharply the **returned singleton value** (a singleton *is* a
shared object — inherent), then the shared **provider** objects (distinct-container
0.92x against thread-local 2.17x is the provider), then the compiled-resolver
closures and their captured cells (every `LOAD_DEREF` of a shared capture increfs
it). The per-container lock is **not** the bottleneck. First-resolve does
additionally serialize on the double-checked creation lock — see
[`2026-08-11-free-threaded-beta-not-stable.md`](../decisions/2026-08-11-free-threaded-beta-not-stable.md),
which states the supported lifecycle contract and the Beta status of free-threaded support.

A throwaway **immortalization experiment** (ctypes set of `ob_ref_local` on the
free-threaded build, offset verified against a known-immortal object) confirmed
the cause and quantified the ceiling: transitively immortalizing the shared
hot-path objects lifts the same-singleton case from ~0.6x to **~2.5x** (median of
3 runs, ≈68% of the ~3.7x machine ceiling).

So it is squarely refcounting, and it *is* recoverable in principle — but the
only lever is unshippable:

- There is **no public API** to immortalize user objects (PEP 683 is internal C-API).
- The `ctypes` poke is free-threaded-build-specific and unsafe.
- Part of the win requires immortalizing the user's **singleton value**, which is
  then never freed — a memory leak, unacceptable in a general-purpose container.

**The fix is CPython's, not ours.** Deferred reference counting expanding to
ordinary instances and cells lifts this for free, with no change here.

Two adjacent benchmark axes were **declined** rather than deferred while this was
measured: a *comparative* override scenario (each framework's override/mock API
differs too much to compare fairly; G12 covers modern-di alone) and an
async-teardown scenario larger than G13's 10 resources (G13's LIFO loop already
captures the scaling).

## Revisit trigger

CPython deferred reference counting expands to cover ordinary instances and cells
— retest G14/G15, which should then scale for free. Or a user reports a real
resolve-throughput bottleneck, which is unlikely: resolution is a tiny fraction of
request work. A comparative version (against that-depends' lock-free slot) stays
out until the two contracts map onto each other fairly.
