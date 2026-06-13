# Alias

`Alias` lets one type resolve to whatever provider already handles a different type. The most common use is binding an abstract base or `Protocol` to a concrete implementation that is already registered, without registering the implementation twice.

Resolving the alias delegates straight back through the container, so overrides and caching on the source provider apply transparently.

## Parameters

### source_type

The type whose registered provider should answer the call. At resolution time, the alias looks up `source_type` in the providers registry and delegates to that provider. If `source_type` is not registered, an `AliasSourceNotRegisteredError` is raised.

### bound_type

The type the alias is registered under in the providers registry — i.e. the type you pass to `container.resolve(...)`. Defaults to `source_type` (which makes the alias a no-op); set it to the abstract or `Protocol` type you want resolvable.

### scope

Standard scope parameter; defaults to `Scope.APP`. The alias does not enforce its own scope-based caching — the source provider's scope governs where the actual instance lives — so the practical effect of `scope` on `Alias` is limited. Setting it to match the source's scope is a reasonable convention.

## Basic Usage

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
        creator=PostgresRepository,
        cache_settings=providers.CacheSettings(),
    )
    abstract_repo = providers.Alias(
        source_type=PostgresRepository,
        bound_type=Repository,
    )


container = Container(groups=[Dependencies])

concrete = container.resolve(PostgresRepository)
abstract = container.resolve(Repository)

# Both resolve to the same instance — the alias delegates to the
# cached source factory.
assert concrete is abstract
```

## Sharing the source's cache

Because `Alias` does not cache anything itself, callers automatically share whatever instance the source provider returns. With a cached `Factory`, every resolution path — by the concrete type, by the abstract type, or via a downstream factory parameter typed as the abstract — returns the same singleton.

With an uncached source `Factory`, each resolution still goes through the source factory, so each call produces a new instance (matching the source factory's own behavior).

## Overrides

Overrides are keyed by `provider_id`, so the alias and its source can be overridden independently:

```python
mock_for_alias = PostgresRepository(dsn="alias-mock")
container.override(Dependencies.abstract_repo, mock_for_alias)

assert container.resolve(Repository) is mock_for_alias
# The source provider is untouched.
assert container.resolve(PostgresRepository) is not mock_for_alias
```

Note: an active override on the alias takes precedence over an override on its source for the aliased type, so reset the alias override first if you want the source override to win.

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

`Alias` participates in `container.validate()` (and `Container(..., validate=True)`):

- If `source_type` is not registered, `AliasSourceNotRegisteredError` is raised eagerly.
- The alias reports the source provider as a dependency, so cycles that pass through an alias are detected and reported via `CircularDependencyError`.

!!! caution "Alias scope is not enforced through `validate()`"
    Because an alias's scope is decorative, `Container.validate()` does **not** check scope
    transitively *through* an alias. A shallow-scoped caller that depends on a deeper-scoped source
    *via* the alias passes validation, then raises `ScopeNotInitializedError` at runtime if it's
    resolved from a container that is too shallow. Bind the alias's `scope` to match the source's so
    the convention reflects where the instance actually lives.
