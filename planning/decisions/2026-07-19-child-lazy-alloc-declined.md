---
status: accepted
summary: Decline lazy-allocating the child-container RLock/CacheRegistry/ContextRegistry — measured saving is ~0 for realistic caching request cycles and ~2-3.5% only for a narrow no-cache child, not worth a resolve hot-path branch plus re-introducing the singleton-creation race.
supersedes: null
superseded_by: null
---

# Decline lazy-allocation of child-container registries

**Decision:** Keep `Container.__init__` eagerly building the per-child `RLock`,
`CacheRegistry`, and `ContextRegistry`. Do not lazy-allocate them.

## Context

After the `_next_deeper` memo (`2026-07-19.02`, #348) took ~40% off default
child-build, the remaining per-child cost was three eager allocations —
`RLock` (~195-214 ns), `CacheRegistry` (~217 ns), `ContextRegistry` (~189 ns).
Deferred work proposed lazy-allocating them (construct on first use) to cut
construction cost, with the net (construction saving vs a resolve hot-path
branch) left "untested." This settles it, starting with the strongest candidate,
the `RLock` (REQUEST children rarely create singletons, so it is the allocation
most often wasted).

## Decision & rationale

Measured ceiling (current `use_lock=True` vs `False`, which already skips the
RLock alloc; py3.10, guidance):

- Isolated child build: RLock alloc ≈ **195 ns/child**.
- **Realistic *caching* request cycle** (build child → resolve a REQUEST-cached
  resource → close, the C4/G7 shape): saving ≈ **0 (0.4%)** — a caching child
  *uses* the lock, so lazy only defers the allocation, and adds a `None`-check.
- Narrow **no-cache child** (transient/APP deps only, no request caching, no
  context): saving ≈ **67 ns (3.5%)** — and this is the ceiling, before any cost.

So the best case is ~0 for the workloads that matter. Real integration request
children inject context (uses `ContextRegistry`) and cache a request-scoped
resource (uses `CacheRegistry` and the `RLock`) — the C4/G7/G9 scenarios all do —
so the trio is *used*, and lazy-allocation saves nothing there while taxing the
hot path. Against a ~0-to-3.5% narrow win, lazy-allocation costs:

1. A `None`-check on the cached-resolve hot path plus a `_use_lock` slot.
2. **Re-introducing the singleton-creation race the lock exists to prevent** —
   lazy lock creation must itself be atomic, so it needs a guard lock or a
   CAS-style publish, a new concurrency-correctness surface against the freshly
   documented Beta contract ([`concurrency.md`](../../architecture/concurrency.md)).

The `CacheRegistry`/`ContextRegistry` variants are *weaker* still: they are used
more often in realistic children, so they save even less. Net negative for a
conservative, zero-dependency library. Decline all three.

## Revisit trigger

A profile of a *realistic* request cycle (with context + caching) showing
child-container construction — specifically these allocations, not `_next_deeper`
— dominating, or a user-reported per-request construction bottleneck in a
build-heavy, cache-free workload (deeply nested short-lived scopes). Re-measure
the net against `G6b` + `G1-G3` + `C4/G7/G9`, and solve the lazy-lock atomicity,
before reopening.
