# Validation is explicit-only; implicit validation was built and discarded

**Decision:** `container.validate()` is the only thing that walks the graph. Neither `__init__` nor
`open()` nor `add_providers` nor `resolve()` ever validates, and `Container(validate=...)` is an
accepted-and-ignored no-op that raises `ValidateArgumentWarning` until 4.0 — 3.0 callers pass
`validate=False` widely, including this repo's own benchmark guards. Shipped as 3.1.0.

3.0 made `open()` mandatory and the sole validation trigger. Both tightenings caused trouble: the
mandatory open produced six production defects across integrations, all one root cause (the root's
open hook does not fire in some execution contexts, so the first unit of work raises); and binding
validation to `open()` produced an authoring rule that existed only because of that binding — open
the root *after* `setup_di`, or a by-type dependency on a not-yet-registered connection fails.

The alternative that kept validation implicit was implemented and worked: split the walk, checking
cycles and inverted scopes eagerly at construction (they are *monotone* — more providers can only
add such an error), and holding completeness on the shared registry to raise at first use (the only
class a later `add_providers` can legitimately fix). It was discarded for the machinery it dragged
in: a two-flag container lifecycle, validation state parked on `ProvidersRegistry`, a
monotone/completeness classification threaded through the walk, and an `add_providers` rollback
path. That is a large permanent surface for a startup-time property, and the cheap way to keep the
guarantee without it — a per-resolve check — taxes the hot path for a concern that matters once, at
boot.

`add_providers` is now a plain register with no rollback; the mutation clears `_validated`, which
`ProvidersRegistry` keeps purely as a memo of a clean walk — it gates nothing, but still
short-circuits the `RecursionError`-to-`CircularDependencyError` guard.

**Measured:** because 3.0 ran a default `validate=True` walk at `open()`, dropping it made
construction markedly cheaper — roughly **2.6 µs against 15.5 µs** for a depth-6 chain
(`Container(...)` + `open()`, default arguments), matching the `test_g10_validate_deep_chain` guard
cost 3.0's `open()` paid. The resolve tier was unchanged, as expected.

**The accepted cost:** the default safety posture drops silently. A broken graph previously raised at
`open()`; now it surfaces from an explicit `validate()`, or at resolve time as
`ArgumentResolutionError`.

**Revisit trigger:** reports of graphs reaching production broken in a way an implicit walk would
have caught at boot — evidence that opt-in `validate()` is under-adopted. Reopen with the adoption
evidence, not with a new mechanism: any replacement must avoid both the four-part machinery above
and a per-resolve check.
