# DuplicateProviderTypeError

## Symptom

```
modern_di.exceptions.registration.DuplicateProviderTypeError: Provider is duplicated by type <class 'myapp.dup.DatabaseConfig'>.
  - Factory (myapp.dup:7)
  - Factory (myapp.dup:10)
Set bound_type=None on one of them to make it resolvable by reference only.
See: https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/
```

It is raised when the second provider is registered: by `Container(groups=[...])` at startup, or by
`container.add_providers(...)`. Each bullet names one provider, the one registered first on top. A
`Factory` is shown by where its creator is declared and any other provider by its repr, so two
factories that share a creator show the same location twice. `.first_provider` and
`.second_provider` hold the provider objects.

The class descends from `RegistrationError`, then `ModernDIError`, then `RuntimeError`, so
`except DuplicateProviderTypeError`, `except RegistrationError` and `except RuntimeError` all catch
it. See [Errors and exceptions](../providers/errors-and-exceptions.md).

## Cause

`modern-di` resolves by type, so each type maps to at most one provider. Two providers end up with the
same `bound_type` when:

- two factories' creators return the same type, such as a primary and a replica `DatabaseConfig`;
- two groups passed to the same container each declare a provider for the type.

The same provider object registered twice raises it too, with both bullets naming one provider and
`.first_provider is .second_provider`. That happens when a group and its subclass are both passed,
when one group is passed twice, or when one provider is assigned in two groups. The hint about
`bound_type=None` does not apply here. Pass each group once, and for a subclass pass only the
subclass, which already holds the base group's providers. This is tracked in
[issue #669](https://github.com/modern-python/modern-di/issues/669).

## Fix

If the two providers stand for different things, give each its own type. A thin subclass is enough,
and each consumer asks for the one it needs:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers
-->

```python
class DatabaseConfig:
    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string


class PrimaryConfig(DatabaseConfig): ...


class ReplicaConfig(DatabaseConfig): ...


class Configs(Group):
    primary = providers.Factory(
        PrimaryConfig, scope=Scope.APP, kwargs={"connection_string": "postgresql://primary"}
    )
    replica = providers.Factory(
        ReplicaConfig, scope=Scope.APP, kwargs={"connection_string": "postgresql://replica"}
    )


container = Container(groups=[Configs])
assert container.resolve(ReplicaConfig).connection_string == "postgresql://replica"
```

Otherwise set `bound_type=None` on one provider to take it out of the by-type lookup, and hand it to
its consumers through `kwargs`. Every provider that would collide needs it, consumers included:

```python
class Repository:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config


class MyGroup(Group):
    primary_db_config = providers.Factory(
        DatabaseConfig,
        scope=Scope.APP,
        kwargs={"connection_string": "postgresql://primary"},
    )
    secondary_db_config = providers.Factory(
        DatabaseConfig,
        scope=Scope.APP,
        bound_type=None,
        kwargs={"connection_string": "postgresql://secondary"},
    )

    primary_repository = providers.Factory(Repository, scope=Scope.APP)
    secondary_repository = providers.Factory(
        Repository,
        scope=Scope.APP,
        bound_type=None,
        kwargs={"db_config": secondary_db_config},
    )


container = Container(groups=[MyGroup])
assert container.resolve(Repository).db_config.connection_string == "postgresql://primary"
secondary = container.resolve_provider(MyGroup.secondary_repository)
assert secondary.db_config.connection_string == "postgresql://secondary"
```

`container.resolve(DatabaseConfig)` and `container.resolve(Repository)` return the primary pair. The
secondary pair is reachable only by reference, through `container.resolve_provider(...)` or as a
`kwargs` value.

To make an abstract type resolve to a concrete implementation, use an [`Alias`](../providers/alias.md)
instead of a second factory.

## See also

- [Factories: `bound_type`](../providers/factories.md#bound_type): how the bound type is inferred and overridden.
- [Alias](../providers/alias.md): binding one type to an already registered provider.
- [ProviderNotRegisteredError](missing-provider.md): the opposite problem, a type with no provider.
- [Errors and exceptions](../providers/errors-and-exceptions.md): where this error sits in the hierarchy.
