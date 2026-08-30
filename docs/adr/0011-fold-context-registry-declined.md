# Keep `ContextRegistry` as its own module

**Decision:** `modern_di/registries/context_registry.py` is not folded into `Container`.
`ContextRegistry` stays a named registry and `ContextProvider` keeps reading it via
`container.context_registry.find_context(...)`.

It is the shallowest of the four registries — ~18 lines, a `dict[type, Any]` behind `find_context`
and `set_context` — and the deletion test on the *code* passes: fold it, and `Container` gains a
`self._context` dict plus a `find_context` method for the two touch points. What the deletion test
misses is that the conceptual slot does not vanish. The four registries are organised by a real
axis, stated in `CLAUDE.md`'s registries entry: shared tree-wide (`providers_registry`,
`overrides_registry`) versus per-container (`cache_registry`, `context_registry`). `ContextRegistry`
sits symmetric with `CacheRegistry`; its shallowness in line count reflects having less mechanism,
not a broken abstraction. Folding trades a uniform 2×2 model for ~18 fewer lines and grows the
already-largest file, with zero actual friction: no bug hides in the one-line delegation, and
context is not a change hot-path. A predictable four-registry pattern navigates better than one with
an exception.

**Revisit trigger:** the four-registry model is restructured — any registry folded, or the
shared-vs-per-container framing abandoned — since the symmetry is the load-bearing reason; or
concrete friction emerges, a bug in the `Container` → `ContextRegistry` delegation, or the
indirection repeatedly obstructing context-related work.
