# No provider registered for type

This error fires when a creator parameter is typed `Foo` and the container has no registered provider for `Foo`.

## Symptom

Resolving an unregistered type directly raises:

```
ProviderNotRegisteredError: No provider is registered for MissingDep.
See: https://modern-di.modern-python.org/troubleshooting/missing-provider/
```

Resolving a registered factory whose creator depends on an unregistered type raises:

```
ArgumentResolutionError: Cannot resolve dependency chain:
  APP  MyService (myapp.missing:7)
  caused by: Argument dep of type <class 'myapp.missing.MissingDep'> cannot be resolved. Trying to build dependency <class 'myapp.missing.MyService'>.
See: https://modern-di.modern-python.org/troubleshooting/argument-resolution-error/
```

The resolver walked the creator's signature, found a parameter typed `MissingDep`, and found nothing for it in the providers registry. The "dependency chain" header shows where in the resolution graph the miss occurred.

## Cause

### 1. The group containing the provider was not passed to `Container`

This is the most common cause. If you split providers across `Database`, `UseCases`, `Cache`, you have to list them all:

<!-- invisible-code-block: python
from modern_di import Container, Group


class Database(Group): ...


class UseCases(Group): ...


class Cache(Group): ...
-->

```python
container = Container(groups=[Database, UseCases, Cache])
container.validate()
```

Missing one group means none of its providers are registered. Calling `container.validate()` at
startup catches this before the first request.

### 2. The creator has no return type annotation

`modern-di` infers the provider's `bound_type` from the creator's return annotation. A creator like `def create_thing(...): ...` (no `-> SomeType`) has no inferable `bound_type` and won't be resolvable by type.

<!-- invisible-code-block: python
import types


class Settings:
    database_url = "postgresql+asyncpg://localhost/app"


sa_async = types.SimpleNamespace(AsyncEngine=type("AsyncEngine", (), {}))
-->

```python
# Broken: cannot resolve by type
def create_engine(settings: Settings):
    return sa_async.create_async_engine(settings.database_url)

# Works: return-typed
def create_engine(settings: Settings) -> sa_async.AsyncEngine:
    return sa_async.create_async_engine(settings.database_url)
```

To fix it, add the return annotation, or set `bound_type=SomeType` on the provider explicitly.

### 3. `bound_type=None` was set on the provider you want to resolve

`bound_type=None` makes the provider unresolvable by type. It's a deliberate opt-out for cases where two providers return the same type (see [Duplicate provider type](duplicate-type-error.md)). If you set it on the wrong provider, the type lookup misses.

Leave `bound_type` at its default on the provider you want resolvable by type. If both providers really do produce the same type, resolve the unresolvable one by reference (`container.resolve_provider(...)`).

### 4. The parameter is a union and the chosen branch isn't registered

For `dep: A | B`, `modern-di` resolves the *first* type in the union order that has a registered provider. If neither is registered, the resolver fails.

Register a provider for one of the union types, or annotate the parameter with a concrete type.

## See also

- [Resolving](../introduction/resolving.md) describes the by-type lookup algorithm.
- [Duplicate provider type](duplicate-type-error.md) covers the inverse problem, where two providers compete for the same type.
- [Factories: `bound_type`](../providers/factories.md) explains how the bound type is inferred and how to override it.
