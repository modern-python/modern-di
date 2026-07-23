---
status: accepted
summary: The provider-type set is closed (Factory, Alias, ContextProvider, container_provider). Retract "Subclassing AbstractProvider" from the documented supported extension points rather than restoring the open dispatch the compiled resolver removed.
supersedes: null
superseded_by: null
---

# Custom providers are not an extension point; the provider set is closed

**Decision:** `modern-di` supports exactly four provider types — `Factory`,
`Alias`, `ContextProvider`, and the pre-built `container_provider`. Subclassing
`AbstractProvider` (or `Factory`) to add a provider type is **not** supported.
The `docs/providers/advanced-api.md` section promising it is retracted rather
than honored.

## Context

Until 2.28.0, `Container.resolve_provider` ended in `provider.resolve(self)` — a
plain polymorphic call. Custom provider support was never designed; it was an
**emergent property** of dispatching through a method. Any subclass implementing
`resolve()` worked automatically, because that is how Python inheritance behaves.
`docs/providers/advanced-api.md` then documented that accident under
"## Supported extension points", with an implement-`resolve(container)` recipe.

The single-path compiled resolver (`2026-07-16.02`, #334) replaced the
polymorphic call with `compile_resolver`, which selects a closure by exact type
identity and rejects everything else:

```python
if type(provider) is Factory:
    ...
if type(provider) is Alias:
    ...
if type(provider) is ContextProvider:
    ...
raise TypeError(f"no compiled resolver for provider type {...}")
```

It also deleted `AbstractProvider.resolve` and `Alias.resolve`, so no hook
survives to fall through to. The closure of the set was deliberate — asserted by
`tests/test_container.py::test_resolve_provider_raises_for_unhandled_provider_type`
and reasoned from in
[2026-07-17-per-provider-compile-seam-declined](2026-07-17-per-provider-compile-seam-declined.md)
("the provider-type set is closed and tiny"). Only the docs were left behind.

Investigation (2026-07-17) established the blast radius and the failure mode:

- **`type(x) is Factory` is identity, not `isinstance`.** A `LoggingFactory(Factory)`
  that overrides nothing at all fails exactly like a from-scratch provider. The
  break is wider than "exotic custom providers".
- **`validate()` cannot catch it.** Validation walks the dependency graph via
  `get_dependencies()`; compilation happens lazily in `resolver_for` at first
  resolve. A container built with `validate=True` reports clean and then raises
  `TypeError` at first resolve, under traffic.
- **Zero consumers.** All 13 sibling `modern-di-*` repos, the two templates, and
  `lite-bootstrap` contain no `AbstractProvider` subclass. (`that-depends` hits
  are that library's own unrelated base class.)

Options weighed: (a) retract the docs and ship 2.29.0; (b) restore a fallback in
2.x behind a `DeprecationWarning` naming the 3.0 removal, matching the
`ContainerClosedWarning` / `ContextValueNoneWarning` / `UnvalidatedContainerWarning`
ramps, and retract at 3.0; (c) hold the whole post-2.28.0 backlog for 3.0.

## Decision & rationale

Chose (a). The capability was never intended, is asserted against by a test, and
has no consumer anywhere in the project's own ecosystem. Restoring an open
dispatch to preserve an accident would re-import the exact indirection #334
removed, and would contradict a decision taken the same day on the same seam.

Rejected (b) — the deprecation ramp — despite it being the house pattern for
2.x→3.0 removals. Those three ramps each guard a capability users demonstrably
rely on; this one would guard an audience believed to be empty, at the cost of
carrying a resurrected fallback path plus a warning class through the 2.x line.
The residual risk is accepted knowingly: an unknown external user subclassing
`Factory` gets a runtime `TypeError` on a minor bump, with `validate()` giving a
false all-clear first. The 2.29.0 notes call this out explicitly under a
breaking-change heading so the release, not the docs, carries the warning.

Rejected (c) — 3.0 is not scoped, and holding the compiled resolver and the perf
work behind it strands shipped, tested work for an unscoped release.

## Revisit trigger

A real user reports a broken custom provider or `Factory` subclass — which would
falsify the zero-audience premise this rests on. At that point the migration path
is the polymorphic `compile()` hook named in
[2026-07-17-per-provider-compile-seam-declined](2026-07-17-per-provider-compile-seam-declined.md)'s
own revisit trigger, not a restored interpreted fallback.
