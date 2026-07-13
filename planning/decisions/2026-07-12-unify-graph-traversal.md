---
status: accepted
summary: Reverse validation.md's "deliberate duplication" stance on the extraction axis — extract the shared graph traversal into a DependencyGraph module while keeping validate() and the runtime guard as distinct policies.
supersedes: null
superseded_by: null
---

# Extract the shared provider-graph traversal, keep the two cycle policies

**Decision:** Extract the provider-graph traversal and cycle-extraction into one
`DependencyGraph` module that `validate()`, the runtime `RecursionError` guard,
and alias scope-resolution all call. Keep the two *policies* distinct
(collect-all vs first-cycle). This reverses, on the extraction axis only, the
duplication `validation.md` currently defends.

## Context

`validation.md` argues the two cycle detectors are a "deliberate duplication,
not a refactor of the one DFS into two callers," because `validate()` collects
all errors while the runtime guard only answers "is a cycle reachable on an
exhausted stack" — and unifying them "would couple the resolve hot path to the
all-errors walker for no user benefit."

That objection targets merging the two **policies** into one walker. It does not
cover the fact that both re-implement the same **traversal + cycle-extraction**
(the `path[cycle_start:]` slice and `CircularDependencyError` construction appear
verbatim in both), and that `Alias.effective_scope` hand-rolls a third
chain-walk. The peer framework dishka confirms the one-walk-many-concerns model
(its `GraphValidator` folds cycle + missing + scope into a single DFS) — it can
drop its runtime guard only because it makes validation effectively mandatory.

## Decision & rationale

The deletion test decides it: with the traversal shared, deleting
`DependencyGraph` makes cycle-detection complexity reappear across all four
callers — a real seam. `validate=False` stays a supported choice after 3.0, so
the runtime guard is *permanent*; two permanent callers of one traversal is a
real seam, not a hypothetical one.

Rejected alternatives:

- **Pure cycle-extraction helper only** — removes the verbatim copy but leaves
  the DFS structure written twice; fails the deletion test.
- **Two traversal methods in the module (recursive walk + iterative find)** —
  still two DFS bodies; relocates the duplication rather than removing it.
- **`DependencyGraph` type-checks `Alias`** to follow the chain — reintroduces
  the concrete-type import coupling the codebase otherwise avoids; instead a
  generic `redirect_target` node hook keeps the module Alias-agnostic.
- **Per-container validated stamp** — a child would not inherit the root's
  validation; the graph is shared, so the stamp is registry-level.
- **Fold scope-inversion into reachability (dishka-style)** — simpler mechanism
  but a less precise error (`missing` vs `inverted`); keep the dedicated
  `InvalidScopeDependencyError`.

## Revisit trigger

Reopen if either holds: (a) benchmarks show the `walk()` event-stream
indirection measurably slows `validate()` or the guard; or (b) `validate=False`
is ever dropped — then the runtime guard disappears, the seam collapses to a
single caller, and the shared module is no longer justified.
