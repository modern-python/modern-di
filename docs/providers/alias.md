# Alias

`Alias` makes one type resolve through the provider already registered for another type. Use it to
bind an abstract base or `Protocol` to a registered implementation without registering the
implementation twice:

```python
import dataclasses
from typing import Protocol

from modern_di import Container, Group, Scope, providers


class Repository(Protocol):
    def fetch(self) -> list[str]: ...


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class PostgresRepository:
    dsn: str = "postgres://localhost"

    def fetch(self) -> list[str]:
        return ["row-1", "row-2"]


class Dependencies(Group):
    repo = providers.Factory(
        PostgresRepository,
        cache=True,
    )
    abstract_repo = providers.Alias(
        PostgresRepository,
        bound_type=Repository,
    )


container = Container(groups=[Dependencies])

concrete = container.resolve(PostgresRepository)
abstract = container.resolve(Repository)

assert concrete is abstract
```

An alias holds no instance and caches nothing, so every resolve goes through the source provider.
With a cached source, as here, the concrete type, the alias type and a downstream parameter typed
as the alias all get the same instance. With an uncached source, each resolve creates a new one.
Aliases chain (an alias whose source type is another alias's `bound_type` works), and an alias can
be wired into `kwargs` like any other provider.

## Parameters

`Alias(source_type, *, bound_type)`. The `source_type` may also be passed as a keyword
(`source_type=`).

### source_type

The type whose registered provider answers the call. The alias looks `source_type` up in the
providers registry and delegates to that provider. If nothing is registered for it, resolving the
alias raises `AliasSourceNotRegisteredError`.

### bound_type

The type the alias is registered under, the one you pass to `container.resolve(...)`. Required. Set
it to the abstract or `Protocol` type you want resolvable, or to `None` to make the alias resolvable
by reference only. An alias bound to its own source type would resolve to itself, so
`bound_type=source_type` raises `AliasBoundToSourceError` at declaration. modern-di does not check
that the source's instances satisfy `bound_type`.

### No scope

`Alias` takes no `scope=`, and a group's default scope does not apply to it. It resolves at its
source's scope: an alias of a REQUEST-scoped factory resolves from a REQUEST container and raises
`ScopeNotInitializedError` from the APP container, the same as its source.

## Overrides

Overrides are keyed by the provider, so the alias and its source can be overridden independently.
See [Testing with overrides](../recipes/testing-overrides.md) for `container.override` and
`reset_override`; the `with container.override(...)` form restores the previous state on exit.

```python
mock_for_alias = PostgresRepository(dsn="alias-mock")
container.override(Dependencies.abstract_repo, mock_for_alias)

assert container.resolve(Repository) is mock_for_alias
assert container.resolve(PostgresRepository) is not mock_for_alias
```

While both are overridden, the alias's override wins for the alias type. Reset the alias override
first if you want the source override to apply to both:

```python
container.reset_override(Dependencies.abstract_repo)
```

Override the source provider instead, and both resolution paths see the mock:

```python
mock_for_source = PostgresRepository(dsn="source-mock")
container.override(Dependencies.repo, mock_for_source)

assert container.resolve(PostgresRepository) is mock_for_source
assert container.resolve(Repository) is mock_for_source
```

## Validation and cycle detection

`container.validate()` treats the source provider as the alias's dependency and reports problems
inside one `ValidationFailedError`:

- `AliasSourceNotRegisteredError` when nothing is registered for `source_type`.
- `CircularDependencyError` for a cycle that passes through an alias; see
  [Troubleshooting: Circular dependency](../troubleshooting/circular-dependency.md).
- `InvalidScopeDependencyError` when a provider depends, through an alias, on a source at a deeper
  scope.

Without `validate()`, the first resolve that reaches the problem raises
`AliasSourceNotRegisteredError`, `CircularDependencyError` or `ScopeNotInitializedError` directly.

```python
class Cache(Protocol): ...


class InMemoryCache: ...


class CacheDependencies(Group):
    cache = providers.Alias(InMemoryCache, bound_type=Cache)


cache_container = Container(groups=[CacheDependencies])
```

<!-- raises: ValidationFailedError -->

```python
cache_container.validate()  # .exceptions holds an AliasSourceNotRegisteredError
```

!!! note "Scope is checked through the alias's source chain"
    `validate()` applies the [scope dependency rule](scopes.md#the-scope-dependency-rule) through
    aliases. The error names every hop of the chain and its terminal source, since the alias's own
    type carries no scope to point at; see
    [Troubleshooting: Scope chain](../troubleshooting/scope-chain.md#when-the-dependency-is-reached-through-an-alias).

## See also

- [Factories: `bound_type`](factories.md#bound_type) — how a provider's registered type is chosen.
- [AliasSourceNotRegisteredError](../troubleshooting/alias-source-not-registered-error.md) — the
  source type has no provider.
- [AliasBoundToSourceError](../troubleshooting/alias-bound-to-source-error.md) — an alias bound to
  its own source type.
- [Testing with overrides](../recipes/testing-overrides.md) — overriding providers in tests.
