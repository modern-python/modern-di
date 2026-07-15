---
status: accepted
summary: Decline folding ContextRegistry into Container — it is a documented, symmetric node in the shared-vs-per-container four-registry model, not incidental co-location, so the ~18-line deletion would break a uniform abstraction for no real friction.
supersedes: null
superseded_by: null
---

# Keep ContextRegistry as its own module

**Decision:** Do not fold `modern_di/registries/context_registry.py` into
`Container` (Candidate 5 from the 2026-07-15 architecture review).
`ContextRegistry` stays a named registry; `ContextProvider` keeps reading it via
`container.context_registry.find_context(...)`.

## Context

`ContextRegistry` is the shallowest of the four registries — ~18 lines, a
`dict[type, Any]` behind `find_context` (returns `UNSET` on miss) and
`set_context`, with no dedicated tests. Its interface is as large as its
implementation, and the deletion test on the *code* passes: fold it, and
`Container` gains a `self._context` dict, keeps `set_context`, and grows a
`find_context` method (a natural sibling to the already-blessed `find_container`
primitive) for the two touch points — `Container.set_context` (write) and
`ContextProvider.fetch_context_value` (read). The review flagged it Speculative
and noted it was originally only worth doing alongside Candidate 3 (the
provider-facing seam), which has since been declined
([2026-07-15-provider-facing-seam-declined](2026-07-15-provider-facing-seam-declined.md)).

Options: (a) fold it and update the docs; (b) decline.

## Decision & rationale

Chose (b). The deciding evidence: **`ContextRegistry` is a documented, symmetric
node in a deliberate model, not incidental co-location.**
`architecture/containers.md` has a "Registry sharing" section that organises the
four registries by a real axis — *shared across the tree* (`ProvidersRegistry`,
`OverridesRegistry`) vs *per-container* (`CacheRegistry`, `ContextRegistry`).
`ContextRegistry` sits symmetric with `CacheRegistry` as one of the two
per-container registries. Its shallowness in line count reflects having less
*mechanism*, not a broken abstraction — its *role* in the model is fully
symmetric.

So the deletion test result is misleading here: the *code*-complexity vanishes,
but the *conceptual* slot does not — `Container` still has per-container context
state; folding merely turns a named registry (symmetric with `CacheRegistry`)
into an unnamed inline dict. That trades a clean, documented, uniform 2×2 model
for ~18 fewer lines, breaks the containers.md table into "three registries + an
inline dict," and grows the already-largest file — all with **zero actual
friction**: no bug hides in the one-line delegation, and context is not a
change hot-path. Uniformity is worth more than the deletion here, and it serves
the same AI-navigability goal the candidate invoked: a predictable four-registry
pattern navigates better than one with an exception.

## Revisit trigger

The **four-registry model is restructured** — any registry folded, or the
shared-vs-per-container framing in `containers.md` abandoned — since the symmetry
is the load-bearing reason to keep it; **or** concrete friction emerges: a bug in
the `Container` → `ContextRegistry` delegation, or the indirection repeatedly
obstructing context-related work.
