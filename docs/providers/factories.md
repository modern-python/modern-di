# Factories

Factories are providers that create instances of dependencies.

## Types of factories 
There are two types of factories:

1. **Regular Factories** - Create a new instance on every call
2. **Cached Factories** - Create an instance once and cache it for future calls

### Regular Factories

Regular factories are initialized on every call.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class IndependentFactory:
    dep1: str
    dep2: int


class Dependencies(Group):
    independent_factory = providers.Factory(
        scope=Scope.APP,
        creator=IndependentFactory,
        kwargs={"dep1": "text", "dep2": 123}
    )


container = Container(groups=[Dependencies])
# Resolve by provider reference
instance = container.resolve_provider(Dependencies.independent_factory)
assert isinstance(instance, IndependentFactory)

# Resolve by type (uses the return type of the creator function/class)
instance2 = container.resolve(IndependentFactory)
assert isinstance(instance2, IndependentFactory)
```

### Cached Factories

Cached factories resolve the dependency only once and cache the resolved instance for future injections.

The caching mechanism is thread-safe by default, ensuring that even when multiple threads attempt to resolve the same cached factory simultaneously, only one instance will be created.

If your application is single-threaded, you can disable the lock for a small performance gain:

```python
container = Container(groups=[Dependencies], use_lock=False)
```

Do not set `use_lock=False` in multi-threaded applications — it removes the guarantee that only one instance is created per cached factory.

```python
import random

from modern_di import Group, Container, Scope, providers


def generate_random_number() -> float:
    return random.random()


class Dependencies(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=generate_random_number,
        cache=True
    )


container = Container(groups=[Dependencies])
singleton_instance1 = container.resolve_provider(Dependencies.singleton)
singleton_instance2 = container.resolve_provider(Dependencies.singleton)

# If resolved in the same container, the instance will be the same
assert singleton_instance1 is singleton_instance2
```

#### Tuning the cache

You can customize caching behavior by passing a `CacheSettings` to `cache=`:

```python
import contextlib

from modern_di import Group, Scope, providers


class SomeResource:
    def close(self) -> None: ...


def create_resource() -> SomeResource:
    # Create and return resource
    return SomeResource()


class Dependencies(Group):
    # Cache with cleanup — clear_cache=True (the default) ensures the closed
    # resource is evicted from cache so it cannot be returned again after close
    resource = providers.Factory(
        scope=Scope.APP,
        creator=create_resource,
        cache=providers.CacheSettings(
            finalizer=lambda res: res.close(),  # Cleanup function
        )
    )
```

## Parameters

When creating a Factory provider, you can configure several parameters:

### scope

Defines the lifetime (scope) of the dependency. Defaults to `Scope.APP`. The available scopes are `APP → SESSION → REQUEST → ACTION → STEP`; see [Scopes](scopes.md) for the full mental model and the dependency rule.

### creator

The callable (function or class) that will be invoked to create instances of the dependency.
Modern-DI analyzes the creator's signature to:
1. Determine the return type (used for `bound_type` if not explicitly set)
2. Identify parameter names and types for automatic dependency resolution

### bound_type

Explicitly sets the type for resolving by type. By default, this is automatically inferred from the creator's return type annotation.
Set to `None` to make the provider unresolvable by type.

### kwargs

Manual values for creator parameters that override automatic dependency resolution.
Use this to provide specific values for parameters or override automatically resolved dependencies.

### cache

Enables caching for the provider. Pass `cache=True` to cache with default settings (no finalizer, cache cleared on close), or `cache=providers.CacheSettings(...)` to tune the finalizer and/or `clear_cache` behavior. Absent, `None`, or `False` means a fresh instance is created on every resolve. See [Lifecycle](lifecycle.md) for how caching, finalizers, and `close_async()` fit together.

`cache_settings=` is a deprecated alias for `cache=` — see [Advanced API](advanced-api.md#deprecated-cache_settings).

### skip_creator_parsing

Disables automatic dependency resolution. When `True`:
- No automatic dependency resolution occurs
- All parameters must be provided via the `kwargs` parameter
- The `bound_type` will not be automatically inferred from the creator's return type; unless `bound_type` is explicitly provided, it defaults to `None`

## Resolution behavior

### Union type parameters

When a parameter is annotated with a union type (e.g. `dep: A | B`), Modern-DI resolves the **first registered type** that matches. The order is determined by how types appear in the union left-to-right. If you rely on a specific type being injected, prefer a concrete type annotation over a union.

### Optional parameters

When a parameter is annotated as `X | None` (or `Optional[X]`), the parameter is treated as optional:

- If a provider for `X` is registered, that provider is resolved and injected as usual.
- If no provider for `X` is registered and the parameter has no default, `None` is injected — no error is raised, and `container.validate()` will not flag the parameter.

This also applies to multi-member optional unions (`A | B | None`): the first registered member is injected, otherwise `None`.

!!! note "Trade-off"
    This is a convenience, but it removes a safety net: if you *intended* to register a provider for an optional dependency and forgot, neither `resolve()` nor `validate()` will report it — the parameter silently receives `None`. For dependencies that must always be present, prefer a non-optional annotation (`dep: X`), which raises `ArgumentResolutionError` when unregistered and is flagged by `validate()`.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


class Cache: ...


@dataclasses.dataclass
class Service:
    cache: Cache | None  # injected if a Cache provider exists, else None


class Dependencies(Group):
    service = providers.Factory(scope=Scope.APP, creator=Service)


container = Container(groups=[Dependencies])
service = container.resolve(Service)
assert service.cache is None  # no Cache provider registered -> None injected
```

### Creator-signature support matrix

The table below summarises how Modern-DI handles each parameter shape during **declaration** (when the `Factory` object is constructed) and **resolution** (when `container.resolve` is called). "Escapes" means the parameter is silently excluded from automatic wiring and must be covered by `kwargs` or a default.

| Parameter shape | Behaviour | When it fails |
|---|---|---|
| `param: SomeClass` — plain type annotation with a registered provider | Resolved and injected automatically. | `ArgumentResolutionError` at resolve if no provider is registered and there is no default. |
| `param: X \| None` / `Optional[X]` | Provider injected if one is registered; otherwise `None`. | Never fails — see [Optional parameters](#optional-parameters). |
| `param: A \| B` — union without `None` | First registered type from the union is injected. | `ArgumentResolutionError` at resolve if neither `A` nor `B` has a registered provider. |
| `param: list[X]` / any parameterized generic | **`UnsupportedCreatorParameterError` at declaration** unless the parameter has a default value or is covered by `kwargs`. | Raised at `Factory(...)` call time. |
| Positional-only param (`def f(x: T, /)`) | **`UnsupportedCreatorParameterError` at declaration** unless the parameter has a default (in which case it is silently skipped). | Raised at `Factory(...)` call time. |
| Unannotated param (`def f(x)`) | Parsed but unresolvable by type. | `ArgumentResolutionError` at resolve unless covered by `kwargs`. |
| Signature whose hints `get_type_hints` cannot resolve (e.g. a forward reference to an undefined name, or — on Python < 3.14 — `functools.partial`) | `UserWarning` is emitted and type-based wiring is skipped; parameters are still parsed (as unannotated). Silence by passing `skip_creator_parsing=True` and an explicit `bound_type`. | A required unannotated param with no provider/default raises `ArgumentResolutionError` at resolve unless covered by `kwargs` (a parameterized-generic or positional-only param still raises `UnsupportedCreatorParameterError` at declaration). |
| `skip_creator_parsing=True` | No wiring at all — every required argument must be supplied via `kwargs`. | `CreatorCallError` at resolve for any missing required argument. |

**Escaping problem shapes** — if a parameter shape would raise at declaration, there are three escape routes, in order of preference:

1. Give the parameter a default value (`def f(items: list[X] | None = None)`).
2. Supply the value via `kwargs={"items": []}` at `Factory` declaration time.
3. Pass `skip_creator_parsing=True` (and supply all required args via `kwargs`).

### Provider passed as a kwargs value

Passing an `AbstractProvider` instance directly as a value in the `kwargs` dict is treated as **explicit wiring**: Modern-DI resolves the provider and injects the resolved value — the provider object itself is never seen by the creator.

```python
from modern_di import Container, Group, Scope, providers


class Backend:
    pass


def make_service(dep: object) -> object:
    ...


class Dependencies(Group):
    backend = providers.Factory(scope=Scope.APP, creator=Backend)
    service = providers.Factory(
        scope=Scope.APP,
        creator=make_service,
        skip_creator_parsing=True,
        bound_type=None,
        kwargs={"dep": backend},  # provider object — resolved at resolve-time
    )


container = Container(groups=[Dependencies])
# make_service receives a Backend instance, not the Factory provider
```

This is useful when `skip_creator_parsing=True` is in effect but you still want dependency injection for some arguments rather than hard-coding concrete values.

### Creator-failure semantics

If a creator raises an exception during resolution:

- **Nothing is cached.** The failed instance is never stored in the cache registry, even if `cache` is set.
- **The next `resolve` call retries.** Subsequent resolves call the creator again from scratch, so a transiently-failing creator will eventually succeed once the underlying condition is fixed.
- **Already-resolved dependencies are not rolled back.** Dependencies that were successfully resolved before the creator raised are still held in their respective containers and will be finalized normally when those containers are closed.

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


attempt = 0


def flaky_creator() -> object:
    global attempt
    attempt += 1
    if attempt == 1:
        raise RuntimeError("transient failure")
    return object()


class Dependencies(Group):
    svc = providers.Factory(
        scope=Scope.APP,
        creator=flaky_creator,
        cache=True,
    )


container = Container(groups=[Dependencies])

try:
    container.resolve(object)
except RuntimeError:
    pass  # first call fails — nothing is cached

result = container.resolve(object)  # retry succeeds
assert result is container.resolve(object)  # now cached
```
