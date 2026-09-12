# One provider-graph traversal, two cycle policies

**Decision:** `DependencyGraph` owns the provider-graph walk and cycle extraction; `validate()`,
the runtime `RecursionError` guard, and alias scope resolution all call it. The two policies stay
distinct (collect every error vs. first cycle), and the runtime guard is permanent since 3.1 made
validation opt-in.

**Why:** before it, both detectors re-implemented the same DFS and `Alias` hand-rolled a third
chain walk. Deleting `DependencyGraph` would make that duplication reappear at four call sites,
which is the test for a real seam. Providers expose only a generic `redirect_target` hook, so the
module stays `Alias`-agnostic; the validated flag lives on the registry because the graph is
shared tree-wide; scope inversion stays a dedicated `InvalidScopeDependencyError` rather than being
folded into reachability, because the precise error is worth more than the simpler walk.
