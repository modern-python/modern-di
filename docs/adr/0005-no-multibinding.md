# No multibinding or collection injection

**Decision:** one type, one provider. No `multi=True`, no `list[T]` fan-in, no binder-set API.

**Why:** the registry is a type → provider map, and multibinding makes it type → collection, which
changes every operation on it: registration stops being "this type is wired" and
`DuplicateProviderTypeError` becomes conditional; `resolve(T)` and `resolve(list[T])` resolve
different things from one registration and the wiring plan needs a third parameter category;
overriding `T` is ambiguous between the collection and one contributor; validation can no longer
tell an empty collection from a wiring mistake. That is permanent structural cost for demand
inferred from other ecosystems. The workaround costs one provider: a `Factory` that takes the
individual dependencies and returns the list.
