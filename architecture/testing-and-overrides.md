# Testing and Overrides

This document describes how `modern-di` supports test isolation via overrides and how tests wire up containers. For
the `modern-di-pytest` integration (a sibling package), see the dedicated section below.

## Overrides

### The OverridesRegistry

`OverridesRegistry` is a thin dataclass holding a single `dict[int, Any]` keyed by `provider_id` (the integer
identity of the provider object). It is created once on the root container and **shared** across the entire container
tree — all child containers hold a reference to the same registry instance.

### container.override and container.reset_override

```python
container.override(provider: AbstractProvider[T], override_object: T) -> OverrideHandle[T]
container.reset_override(provider: AbstractProvider[T] | None = None) -> None
```

`container.override(provider, obj)` writes `obj` into the shared `OverridesRegistry` under the provider's id and
returns an `OverrideHandle[T]`, generic over the override object's type. The override is active from the `override()`
call itself, not from `__enter__` — imperative callers that discard the handle see identical behavior to before.
Used as a context manager, the handle's `__exit__` restores the snapshot taken at the `override()` call — the
provider's prior override if one existed, otherwise no override — unconditionally, even on exception and even if
`reset_override()` ran inside the block. Nested overrides of the same provider unwind in order, each handle
restoring what was active before it. The `OverridesRegistry` itself stays a flat dict; the stack lives in the
handles, not the registry. `container.reset_override(provider)` removes that entry directly. Calling
`reset_override()` with no argument (or `None`) clears **all** overrides from the registry.

Because the registry is shared, calling either method on a child container has the same effect as calling it on the
root — the override is visible tree-wide. `close_async` and `close_sync` on the root container also call
`reset_override()` automatically, clearing all overrides when the root is torn down.

### How overrides short-circuit resolution

`resolve_provider` checks the override registry before delegating to the provider — see
[resolution.md](resolution.md)'s Step 1 for the mechanism. The override value is
returned directly, bypassing the scope check, cache lookup, and creator invocation. This means the override
object does not need to be an instance of the provider's declared type at runtime (Python does not enforce it),
but callers should pass a compatible object for type safety.

### Scope behaviour under overrides

An overridden provider is resolved from whichever container `resolve_provider` is called on — the scope of the
original provider is irrelevant because the short-circuit fires before `find_container`. In practice this means a
REQUEST-scoped provider can be overridden and resolved from an APP container without raising
`ScopeNotInitializedError`, which is often what tests want.

Overrides do not interact with the cache. If a singleton (cached factory) was already resolved before
`container.override(...)` is called, subsequent calls to `resolve_provider` return the override value, not the
cached instance. After `reset_override`, the original cache entry (if any) is still present and is returned again.

## Testing patterns

Declare providers as `Group` class attributes and pass the group to `Container` (see
[containers.md](containers.md#creating-a-root-container)). Resolve by provider reference
(`resolve_provider`, most precise) or by type (`resolve`) — both go through the override check.
Test deeper scopes via `build_child_container`; each child gets its own cold `cache_registry` (see
[Registry sharing](containers.md#registry-sharing)), so a request-scoped provider resolved in one
child never leaks a cached instance into another. Inject overrides with
`container.override(provider, obj)` — visible tree-wide immediately, since `OverridesRegistry` is
shared (see above) — and reset with `reset_override()`, or rely on the root container's
`close_sync`/`close_async` to clear all overrides automatically at teardown.

## modern-di-pytest integration

`modern-di-pytest` is a **separate package** in a sibling repository. `modern-di` does not depend on it.

The package exposes two callables for turning DI providers into pytest fixtures:

**`modern_di_fixture(type_or_provider)`** — creates a single pytest fixture that resolves the given type or
provider from a container fixture already present in the test session.

**`expose(*groups)`** — bulk-generates one pytest fixture per provider across one or more `Group` subclasses.
Duplicate attribute names across the supplied groups raise `ValueError`. The generated fixtures are named after the
attribute and resolve the corresponding provider automatically.

Both callables are meant to be used at module level (or in a `conftest.py`) to declare fixtures. At test time,
requesting a fixture by name resolves the provider through the normal `resolve_provider` path, which means overrides
applied to the container before the fixture is invoked are honoured.
