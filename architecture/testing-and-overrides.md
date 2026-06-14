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
container.override(provider: AbstractProvider[T], override_object: T) -> None
container.reset_override(provider: AbstractProvider[T] | None = None) -> None
```

`container.override(provider, obj)` writes `obj` into the shared `OverridesRegistry` under the provider's id.
`container.reset_override(provider)` removes that entry. Calling `reset_override()` with no argument (or `None`)
clears **all** overrides from the registry.

Because the registry is shared, calling either method on a child container has the same effect as calling it on the
root — the override is visible tree-wide. `close_async` and `close_sync` on the root container also call
`reset_override()` automatically, clearing all overrides when the root is torn down.

### How overrides short-circuit resolution

`resolve_provider` checks the registry before delegating to the provider:

```python
def resolve_provider(self, provider):
    if self.overrides_registry.overrides and \
       (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET:
        return override          # returned immediately, no cache, no factory call
    return provider.resolve(self)
```

The override value is returned directly, bypassing the scope check, cache lookup, and creator invocation. This
means the override object does not need to be an instance of the provider's declared type at runtime (Python does
not enforce it), but callers should pass a compatible object for type safety. See `resolution.md` for the full
resolution flow that overrides short-circuit.

### Scope behaviour under overrides

An overridden provider is resolved from whichever container `resolve_provider` is called on — the scope of the
original provider is irrelevant because the short-circuit fires before `find_container`. In practice this means a
REQUEST-scoped provider can be overridden and resolved from an APP container without raising
`ScopeNotInitializedError`, which is often what tests want.

Overrides do not interact with the cache. If a singleton (cached factory) was already resolved before
`container.override(...)` is called, subsequent calls to `resolve_provider` return the override value, not the
cached instance. After `reset_override`, the original cache entry (if any) is still present and is returned again.

## Testing patterns

### Declaring providers

Define a `Group` subclass with providers as class-level attributes and pass it to `Container`:

```python
from modern_di import Container, Scope, providers, Group

class MyGroup(Group):
    service               = providers.Factory(scope=Scope.APP, creator=MyService)
    repo                  = providers.Factory(scope=Scope.APP, creator=MyRepo)
    request_scoped_service = providers.Factory(scope=Scope.REQUEST, creator=RequestScopedService)

container = Container(scope=Scope.APP, groups=[MyGroup])
```

### Resolving in tests

Resolve by provider reference (most precise — no type lookup):

```python
instance = container.resolve_provider(MyGroup.service)
```

Resolve by type (matches the type registered in `ProvidersRegistry`):

```python
instance = container.resolve(MyService)
```

Both methods go through `resolve_provider` and therefore respect overrides.

### Testing scope chains

Build child containers to test providers that require a deeper scope:

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup])
request_container = app_container.build_child_container(scope=Scope.REQUEST)
instance = request_container.resolve_provider(MyGroup.request_scoped_service)
request_container.close_sync()
```

Child containers share the parent's `providers_registry` and `overrides_registry` but have independent
`cache_registry` instances, so each child starts with a cold cache.

### Injecting overrides

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup])
app_container.override(MyGroup.repo, FakeRepo())

result = app_container.resolve_provider(MyGroup.service)  # receives FakeRepo

app_container.reset_override(MyGroup.repo)   # restore
```

Overrides set on the app container are visible in all child containers built afterward (shared registry), and in
child containers already in existence too, since the registry object is the same reference.

### Cleanup

Call `container.reset_override()` (no argument) after a test to clear all overrides, or rely on
`close_sync`/`close_async` on the root container — both clear the registry automatically.

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
