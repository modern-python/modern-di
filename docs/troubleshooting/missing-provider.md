# No provider registered for type

This error fires when a creator parameter is typed `Foo` and the container has no registered provider for `Foo`.

## Understanding the error

**Direct miss** — resolving an unregistered type directly:

```
ProviderNotRegisteredError: Provider of type <class 'SomeType'> is not registered in providers registry.
```

**Nested miss** — a registered factory whose creator depends on an unregistered type:

```
ArgumentResolutionError: Cannot resolve dependency chain:
  APP  MyService
  caused by: Argument dep of type <class 'MissingDep'> cannot be resolved. Trying to build dependency <class 'MyService'>.
```

The resolver walked the creator's signature, found a parameter typed `MissingDep`, and looked it up in the providers registry — nothing was there. The "dependency chain" header shows where in the resolution graph the miss occurred.

## Common causes

### 1. The group containing the provider was not passed to `Container`

Most common. If you split providers across `Database`, `UseCases`, `Cache`, you have to list them all:

```python
container = Container(groups=[Database, UseCases, Cache], validate=True)
```

Missing one group means none of its providers are registered. `validate=True` catches this at startup.

### 2. The creator has no return type annotation

`modern-di` infers the provider's `bound_type` from the creator's return annotation. A creator like `def create_thing(...): ...` (no `-> SomeType`) has no inferable `bound_type` and won't be resolvable by type.

```python
# ❌ Cannot resolve by type
def create_engine(...):
    return sa_async.create_async_engine(...)

# ✅ Return-typed
def create_engine(...) -> sa_async.AsyncEngine:
    return sa_async.create_async_engine(...)
```

Fix: add the return annotation, or set `bound_type=SomeType` on the provider explicitly.

### 3. `bound_type=None` was set on the provider you want to resolve

`bound_type=None` makes the provider unresolvable by type. It's a deliberate opt-out for cases where two providers return the same type (see [Duplicate Type Error](duplicate-type-error.md)). If you set it on the wrong provider, the type lookup misses.

Fix: leave `bound_type` at its default on the provider you want resolvable by type. If both providers really do produce the same type, resolve the unresolvable one by reference (`container.resolve_provider(...)`).

### 4. The parameter is a union and the chosen branch isn't registered

For `dep: A | B`, `modern-di` resolves the *first* type in the union order that has a registered provider. If neither is registered, the resolver fails.

Fix: register a provider for one of the union types, or annotate the parameter with a concrete type.

## See also

- [Resolving](../introduction/resolving.md) — the by-type lookup algorithm.
- [Duplicate Type Error](duplicate-type-error.md) — the inverse problem, where two providers compete for the same type.
- [Factories: `bound_type`](../providers/factories.md) — how the bound type is inferred and how to override it.
