---
status: accepted
summary: Drop the warm-singleton resolver memo-swap — built, fully tested, and measured at ~1.6x (short of the pre-committed 2x gate, because `resolve_provider`'s dispatch floor is unremovable by the swap); a bounded win does not buy a permanent cross-cutting invalidation invariant.
supersedes: null
superseded_by: null
---

# Drop the warm-singleton resolver memo-swap

**Decision:** `modern-di` does not self-modify its resolver memo after a
singleton is built. The warm-singleton hit keeps paying the normal compiled-cached
resolver path. The mechanism was implemented in full, measured, and reverted.

## Context

The single-path compiled resolver (#334) left one perf lever open: the warm
singleton hit was 292 ns, against dishka ~245 ns, wireup ~98 ns, that-depends
~85 ns, and dependency-injector ~61 ns. modern-di paid `resolver_for` dispatch,
the override front-guard, and `fetch_cache_item` on *every* warm hit.

wireup's technique is to swap the cached provider's stored resolver for a bare
`return value` closure once the value exists. Adapting it here is constrained by
modern-di's shared-registry / per-container-cache split: the resolver lives
tree-wide on `ProvidersRegistry` while the cached value is per-container, so a
bare swap is only sound for **APP-scoped** singletons, where a clean
1:1:1 holds — one registry ↔ one APP container ↔ one tree-wide value. Deeper
scopes cache per child container, so a registry-level constant would be wrong.

This was run as a **measurement-gated spike** with a pre-committed kill-gate:
ship iff the warm hit reached ≤ ~146 ns (at least halved) *and* beat dishka,
with zero correctness regression and a green free-threaded stress test.

## Decision & rationale

The mechanism was built exactly as designed — APP-scope predicate, install on
the cold-miss branch after `mark_created`, `_warm_original` for O(1) restore,
and invalidation across registry mutation (version bump), `override()`
(un-swap the pid), and root close (invalidate all, which also restores the
closed-container warn/reopen shim a bare closure would bypass). It passed the
free-threaded stress test at `--count=100` (200/200) and `test-ci` at 100%
coverage.

**Measured** (best-of-3, stable medians, machine-relative): guard g2 warm hit
584 → 375 ns; comparative C2 333 → 208 ns. A consistent **~1.6x** reduction —
enough to flip modern-di ahead of dishka (292 ns), but short of the ≤146 ns gate.

**Root cause of the shortfall:** `resolve_provider`'s dispatch floor — the
`_warn_and_reopen_if_closed` frame, the `resolver_for` dict lookup, and the
version check — is not removable by the swap. Unlike wireup, modern-di keeps the
resolve → `resolver_for` dispatch, so "near-free" was never architecturally
reachable by this technique. The swap optimizes the closure body; the floor is
upstream of it.

**The ruling:** a ~1.6x win does not justify a permanent cross-cutting
invariant — a bypass resolver spanning `override` / `close` / `add_providers`,
plus a second source of truth in `_warm_swapped` — against the
conservative-feature-set and legibility principles. Below the bar, nothing ships
but the measurement.

Two things from the attempt were kept:

1. The free-threaded stress test surfaced that close-during-resolve was not
   torn-free. The research it triggered established that the
   build → resolve → dispose lifecycle with single-threaded teardown is the
   universal field standard, now stated explicitly in
   [`concurrency.md`](../../architecture/concurrency.md).
2. It revealed a better direction — the **dispatch-floor simplification**
   (invalidate-on-mutation instead of a version stamp per resolve), which
   *removes* per-resolve work instead of adding a bypass and is licensed by that
   now-explicit lifecycle contract. It shipped in #347.

The revert restored `providers_registry.py`, `resolver_compiler.py`,
`container.py`, and their tests; `concurrency.md` was kept.

## Revisit trigger

A user-reported warm-singleton bottleneck **plus** a design that removes the
dispatch floor itself — the swap alone provably cannot clear the bar, so
re-proposing it unchanged is settled. The open perf question is tracked
separately as a deferred item; this decision governs only the memo-swap
technique. A that-depends-style per-APP-container slot array was explicitly not
pre-authorized here and would need its own measurement.
