# Validation is explicit-only

**Decision:** `container.validate()` is the only thing that walks the graph. Construction,
`open()`, `add_providers` and `resolve()` never validate. `Container(validate=...)` is accepted
and ignored with `ValidateArgumentWarning` until 4.0. Shipped in 3.1.0.

**Why:** 3.0 made `open()` mandatory and the sole validation trigger; that caused six production
defects with one root cause (the root's open hook does not fire in some execution contexts) and an
authoring rule that existed only because of the binding. An implicit alternative was built and
worked (monotone checks at construction, completeness at first use) and was discarded for the
machinery it dragged in: a two-flag lifecycle, validation state on the registry, a
monotone/completeness classification through the walk, and an `add_providers` rollback. Dropping the
default walk also made construction roughly 2.6 µs instead of 15.5 µs for a depth-6 chain. The
accepted cost is that a broken graph surfaces from an explicit `validate()` or at resolve time.
