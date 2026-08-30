# Drop the warm-singleton resolver memo-swap

**Decision:** the resolver memo is never self-modified after a singleton is built; a warm
singleton hit keeps paying the normal compiled-resolver path. The mechanism was built in full,
measured, and reverted.

wireup's technique — swap a cached provider's stored resolver for a bare `return value` closure
once the value exists — is sound here only for **APP** scope, where one registry ↔ one APP
container ↔ one tree-wide value holds; deeper scopes cache per child container, so a
registry-level constant would be wrong. It was run as a measurement-gated spike with a
pre-committed gate: ship iff the warm hit reached ≤ ~146 ns (at least halved) *and* beat dishka,
with zero correctness regression and a green free-threaded stress test.

**Measured** (best-of-3, stable medians, machine-relative): guard g2 warm hit 584 → 375 ns;
comparative C2 333 → 208 ns. A consistent **~1.6x**, enough to pass dishka (292 ns), short of the
≤146 ns gate. The shortfall is structural: `resolve_provider`'s dispatch floor — the
closed-container shim frame, the `resolver_for` lookup, the version check — sits upstream of the
closure body the swap replaces, so "near-free" was never architecturally reachable this way. A
~1.6x win does not buy a permanent cross-cutting invalidation invariant: a bypass resolver
spanning `override()` / `close()` / `add_providers()`, plus a second source of truth in
`_warm_swapped`.

Two things from the attempt were kept: the free-threaded stress test surfaced that
close-during-resolve was not tear-free, and the research it triggered is now stated in
[design decisions](../introduction/design-decisions.md#the-thread-safety-boundary); and it pointed
at the dispatch-floor simplification (invalidate-on-mutation instead of a per-resolve version
stamp), which *removes* per-resolve work and shipped in #347.

**Revisit trigger:** a user-reported warm-singleton bottleneck **plus** a design that removes the
dispatch floor itself — the swap alone provably cannot clear the bar, so re-proposing it unchanged
is settled. This record governs the memo-swap technique only; a that-depends-style
per-APP-container slot array was not pre-authorized here and would need its own measurement.
