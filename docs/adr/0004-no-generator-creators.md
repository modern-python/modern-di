# No generator creators in core `Factory`

**Decision:** `Factory` does not treat a generator creator as "yield the value, run the rest as a
finalizer". `CacheSettings(finalizer=)` is the only teardown spelling in core.

**Why:** every Python peer spells teardown as code after `yield`, so this is the strongest
muscle-memory delta for migrants, but adopting it is breaking (`Factory(creator=generator_fn)` is
legal today and resolves to the generator) and carries open design: per-instance finalizer records
for uncached factories, rejecting async generators at declaration, extracting `bound_type` from
`Iterator[T]`. One explicit spelling also keeps the property that async finalizers work under sync
resolution, which the generator form cannot express. A `Factory` subclass in userland can wrap a
generator creator and register the continuation through `CacheSettings(finalizer=)`.
