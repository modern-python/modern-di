# ProviderNotRegisteredError

`container.resolve(SomeType)` raises this when no provider is registered under `SomeType`. When the
missing type is a parameter of a registered provider's creator, the error is
[`ArgumentResolutionError`](argument-resolution-error.md) instead.

## Symptom

```
modern_di.exceptions.resolution.ProviderNotRegisteredError: No provider is registered for MissingDep.
See: https://modern-di.modern-python.org/troubleshooting/missing-provider/
```

When a subclass, a base class or a similarly named type is registered, the message lists it:

```
modern_di.exceptions.resolution.ProviderNotRegisteredError: No provider is registered for Clock.
Did you mean:
  - SystemClock (registered subclass, scope=APP)
See: https://modern-di.modern-python.org/troubleshooting/missing-provider/
```

`.dependency_type` holds the type you asked for, and `.suggestions` holds the "Did you mean" entries.

## Cause

### 1. The group containing the provider was not passed to `Container`

If you split providers across `Database`, `UseCases` and `Cache`, list them all:

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

Leaving out a group leaves out all of its providers. `container.validate()` at startup catches the
gap when another registered provider depends on one of the missing types, and reports it as an
`ArgumentResolutionError` inside [`ValidationFailedError`](validation-failed-error.md). A type that
your code only resolves directly is invisible to `validate()`, so that miss still surfaces at the
first `resolve`.

### 2. The creator has no return type annotation

`modern-di` takes the provider's `bound_type` from the creator's return annotation. A creator without
`-> SomeType` gets `bound_type=None`, so the provider is reachable only by reference:

<!-- invisible-code-block: python
from modern_di import Scope, providers


class Engine: ...
-->

<!-- raises: ProviderNotRegisteredError -->

```python
# Broken:
def create_engine():
    return Engine()


container = Container(groups=[])
container.add_providers(providers.Factory(create_engine, scope=Scope.APP))
container.resolve(Engine)
```

Add the return annotation, or pass `bound_type=Engine` to the provider:

```python
# Works:
def create_engine() -> Engine:
    return Engine()


container = Container(groups=[])
container.add_providers(providers.Factory(create_engine, scope=Scope.APP))
assert isinstance(container.resolve(Engine), Engine)
```

### 3. `bound_type=None` was set on the provider you want to resolve

`bound_type=None` takes a provider out of the by-type lookup. It is the opt-out for two providers that
return the same type (see [DuplicateProviderTypeError](duplicate-type-error.md)), and setting it on
the wrong one makes the lookup miss. Leave `bound_type` at its default on the provider you resolve by
type, and resolve the other one by reference with `container.resolve_provider(...)`.

## See also

- [Resolving dependencies](../introduction/resolving.md): the by-type lookup.
- [ArgumentResolutionError](argument-resolution-error.md): the same gap, hit by a creator parameter.
- [DuplicateProviderTypeError](duplicate-type-error.md): two providers competing for one type.
- [Factories: `bound_type`](../providers/factories.md#bound_type): how the bound type is inferred and overridden.
