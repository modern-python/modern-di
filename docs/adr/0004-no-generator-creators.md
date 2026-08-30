# No generator creators in core `Factory`

**Decision:** `Factory` does not auto-detect generator creators and turn post-`yield` code into a
finalizer; `CacheSettings(finalizer=)` remains the only teardown spelling in core.

Every Python peer — dishka, wireup, svcs, FastAPI yield-dependencies, that-depends `Resource` —
spells teardown as code after `yield`, making it the strongest muscle-memory delta for migrants. It
was rejected because the change is breaking (`Factory(creator=generator_fn)` is legal today and
resolves to the raw generator object) and carries open design complexity: per-instance finalizer
records for non-cached factories, declaration-time rejection of async generators, and `bound_type`
extraction from `Iterator[T]`. That is a large addition against a modest ergonomic win, and the
capability is reachable without core changes — a `Factory` subclass in userland or a sibling package
can wrap a generator creator and register the continuation through `CacheSettings(finalizer=)`. One
explicit teardown spelling also preserves the property that async finalizers work under sync
resolution, which the generator form cannot express.

**Revisit trigger:** recurring user requests for yield-based teardown, or a community-built
generator-factory subclass demonstrating both the demand and a settled design.
