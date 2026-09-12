# The provider set is closed; custom providers are not an extension point

**Decision:** modern-di supports exactly four provider types: `Factory`, `Alias`, `ContextProvider`
and the pre-built `container_provider`. Subclassing `AbstractProvider` or `Factory` to add a type
is not supported; the docs section that promised it was retracted.

**Why:** custom providers were never designed. Until 2.28.0 `resolve_provider` ended in
`provider.resolve(self)`, so any subclass with a `resolve()` worked as an accident of inheritance,
and the docs wrote the accident down. The single-path compiler dispatches on exact type identity and
raises otherwise, so a `LoggingFactory(Factory)` that overrides nothing fails at first resolve, and
`validate()` cannot catch it because compilation is lazy. All thirteen sibling integration repos,
both templates and `lite-bootstrap` contain no subclass, so the risk was accepted and recorded in
the 2.29.0 notes rather than guarded by a deprecation fallback that would resurrect the removed
indirection. Should a real subclass ever surface, the migration path is a polymorphic `compile()`
hook, not a restored interpreted fallback.
