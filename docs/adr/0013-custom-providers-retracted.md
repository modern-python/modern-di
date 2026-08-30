# Custom providers are not an extension point; the provider set is closed

**Decision:** `modern-di` supports exactly four provider types — `Factory`, `Alias`,
`ContextProvider`, and the pre-built `container_provider`. Subclassing `AbstractProvider` (or
`Factory`) to add a provider type is **not** supported; the `docs/providers/advanced-api.md` section
promising it was retracted rather than honoured.

Custom provider support was never designed. Until 2.28.0, `resolve_provider` ended in
`provider.resolve(self)`, so any subclass implementing `resolve()` worked — an emergent property of
Python inheritance that the docs then wrote down. The single-path compiled resolver (#334) replaced
that with `compile_resolver`, which selects a closure by exact type identity and raises otherwise,
and deleted `AbstractProvider.resolve` and `Alias.resolve`, so no hook survives to fall through to.
The closure was deliberate — asserted by
`tests/test_container.py::test_resolve_provider_raises_for_unhandled_provider_type`. Only the docs
were left behind.

The blast radius and failure mode: `type(x) is Factory` is identity, not `isinstance`, so a
`LoggingFactory(Factory)` that overrides nothing fails exactly like a from-scratch provider;
`validate()` cannot catch it, since compilation is lazy, so a container reports clean and then
raises `TypeError` at first resolve under traffic. Against that: **zero consumers** — all 13 sibling
`modern-di-*` repos, the two templates, and `lite-bootstrap` contain no `AbstractProvider` subclass.

Rejected: a 2.x fallback behind a `DeprecationWarning`, matching the `ContainerClosedWarning` /
`ContextValueNoneWarning` / `UnvalidatedContainerWarning` ramps. Those guard capabilities users
demonstrably rely on; this one would guard an audience believed empty, at the cost of resurrecting
the exact indirection #334 removed and carrying it through the 2.x line. The residual risk is
accepted knowingly, and the 2.29.0 notes carry it under a breaking-change heading. Also rejected:
holding the whole post-2.28.0 backlog for an unscoped 3.0.

**Revisit trigger:** a real user reports a broken custom provider or `Factory` subclass, falsifying
the zero-audience premise. The migration path is then the polymorphic `compile()` hook named in
[the per-provider compile seam](0014-per-provider-compile-seam-declined.md), not a restored
interpreted fallback.
