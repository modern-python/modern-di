# Decline lazy-allocation of child-container registries

**Decision:** `Container.__init__` keeps eagerly building the per-child `RLock`, `CacheRegistry`,
and `ContextRegistry`. They are not lazy-allocated.

**Measured** ceiling (`use_lock=True` vs `False`, which already skips the RLock alloc; py3.10,
guidance), starting from the strongest candidate — the `RLock`, since REQUEST children rarely create
singletons:

- Isolated child build: RLock alloc ≈ **195 ns/child** (`CacheRegistry` ≈ 217 ns, `ContextRegistry`
  ≈ 189 ns).
- **Realistic caching request cycle** (build child → resolve a REQUEST-cached resource → close, the
  C4/G7 shape): saving ≈ **0 (0.4%)** — a caching child *uses* the lock, so lazy only defers the
  allocation and adds a `None`-check.
- Narrow **no-cache child** (transient/APP deps only): saving ≈ **67 ns (3.5%)**, and that is the
  ceiling before any cost.

Real integration request children inject context and cache a request-scoped resource — the C4/G7/G9
scenarios all do — so the trio is used and lazy-allocation saves nothing there while taxing the hot
path. Against a 0-to-3.5% narrow win it costs a `None`-check on the cached-resolve hot path plus a
`_use_lock` slot, and **re-introduces the singleton-creation race the lock exists to prevent**:
lazy lock creation must itself be atomic, so it needs a guard lock or a CAS-style publish, a new
concurrency-correctness surface against the documented Beta contract in
[design decisions](../introduction/design-decisions.md#the-thread-safety-boundary). The
`CacheRegistry` / `ContextRegistry` variants are weaker still — used more often in realistic
children, so they save even less.

**Revisit trigger:** a profile of a *realistic* request cycle (context + caching) showing these
allocations — not `_next_deeper` — dominating, or a user-reported per-request construction
bottleneck in a build-heavy, cache-free workload. Re-measure the net against `G6b` + `G1-G3` +
`C4/G7/G9`, and solve the lazy-lock atomicity, before reopening.
