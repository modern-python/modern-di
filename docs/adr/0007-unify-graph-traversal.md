# Extract the shared provider-graph traversal, keep the two cycle policies

**Decision:** one `DependencyGraph` module owns the provider-graph traversal and cycle extraction;
`validate()`, the runtime `RecursionError` guard, and alias scope-resolution all call it. The two
*policies* stay distinct (collect-all vs first-cycle).

Before it, both detectors re-implemented the same traversal — the `path[cycle_start:]` slice and
`CircularDependencyError` construction appeared verbatim in each — and `Alias.effective_scope`
hand-rolled a third chain-walk. With the traversal shared, deleting `DependencyGraph` makes
cycle-detection complexity reappear across all four callers: a real seam, not a hypothetical one.
dishka confirms the one-walk-many-concerns model; it can drop its runtime guard only because it
makes validation effectively mandatory.

Rejected alternatives:

- **A pure cycle-extraction helper.** Removes the verbatim copy but leaves the DFS structure written
  twice; fails the deletion test.
- **Two traversal methods in the module** (recursive walk + iterative find). Relocates the
  duplication rather than removing it.
- **Type-checking `Alias` inside `DependencyGraph`** to follow the chain. Reintroduces concrete-type
  import coupling; a generic `redirect_target` node hook keeps the module Alias-agnostic.
- **A per-container validated stamp.** A child would not inherit the root's validation; the graph is
  shared, so the stamp is registry-level.
- **Folding scope-inversion into reachability (dishka-style).** Simpler, but yields a less precise
  error (`missing` vs `inverted`); the dedicated `InvalidScopeDependencyError` is worth more.

**Revisit trigger:** benchmarks show the `walk()` event-stream indirection measurably slows
`validate()` or the guard. The original second limb — validation becoming mandatory, collapsing the
seam to one caller — is retired: 3.1 went the other way, so the runtime guard is permanent.
