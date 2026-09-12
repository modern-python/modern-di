# Keep `ContextRegistry` as its own module

**Decision:** the context registry is not folded into `Container`; `ContextProvider` keeps reading
it through `container.context_registry`.

**Why:** it is the shallowest registry (a dict behind `find_context` / `set_context`) and folding it
would pass the deletion test on code, but the four registries are organised on a real axis: shared
tree-wide (providers, overrides) versus per-container (cache, context). Folding one trades a
uniform 2x2 model for eighteen fewer lines and a larger `Container`, with no friction removed:
nothing hides in the one-line delegation and context is not a hot path.
