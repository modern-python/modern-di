# A scope violation draws the chain that reached it, at effective scope

**Decision:** `InvalidScopeDependencyError` renders the same arrow tree as every other
chain-shaped error, and each redirect hop is drawn at the scope it resolves at, not the scope the
provider object reports. The redirect walk is one module-level `terminal_chain()` in the graph
module; `.dep_chain` joins the attribute surface with `.dep_provider` and `.dep_terminal` as its
ends. `RegistrationError` stays the base class because the hierarchy is the contract.

**Why:** the old message named the alias's bound type beside a scope belonging to the provider at
the far end of the chain, and the provider to change never appeared. A cycle through the same alias
already drew every hop, so two errors from one `validate()` disagreed, the drift
[ADR-0009](0009-error-text-is-not-a-contract.md) exists to prevent. Drawing declared scope prints
`APP APP APP REQUEST` for a three-hop chain and points at the wrong fix; blanking the column
supplies nothing; drawing each hop at its terminal's scope puts the boundary on the offending edge.
`Alias.scope` still returns `APP`, since ordering depends on it: this is a rendering rule. The walk
moved into the graph module rather than being copied, because `Alias` cannot import it and
[ADR-0007](0007-unify-graph-traversal.md) keeps one traversal. The rule assumes a redirect owns no
lifetime of its own, which is true of `Alias` and of nothing else.
