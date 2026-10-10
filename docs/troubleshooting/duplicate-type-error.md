# DuplicateProviderTypeError

This error occurs when two or more providers are registered with the same `bound_type`. `modern-di` uses the `bound_type` to resolve dependencies by type, so each type must be unique in the providers registry.

## Symptom

When you see this error:

```
modern_di.exceptions.registration.DuplicateProviderTypeError: Provider is duplicated by type <class 'SomeType'>.
  - Factory (myapp.ioc:12)
  - Factory (myapp.other:30)
Set bound_type=None on one of them to make it resolvable by reference only.
See: https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/
```

Each line names one of the two providers, the one registered first on top: a `Factory` by where its
creator is declared, any other provider by its repr. `.first_provider` and `.second_provider` hold
the provider objects.

It descends from `RegistrationError` → `ModernDIError` → `RuntimeError`, so `except DuplicateProviderTypeError`, `except RegistrationError`, and `except RuntimeError` all catch it. See [Errors and exceptions](../providers/errors-and-exceptions.md).

This typically happens when:

1. You have multiple factories that return the same type
2. You're using the same class in different contexts with different configurations

## Fix

Set `bound_type=None` on one of the duplicate providers to make it unresolvable by type. A factory
that needs that provider then gets it explicitly through `kwargs`, since resolving by type finds only
the other one. The example below does both:

```python
from modern_di import Group, Scope, providers


class DatabaseConfig:
    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string


class Repository:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config


class MyGroup(Group):
    # Step 1: Set bound_type=None on the secondary provider or for both providers
    # This provider can be resolved by type: container.resolve(DatabaseConfig)
    primary_db_config = providers.Factory(
        DatabaseConfig,
        scope=Scope.APP,
        kwargs={"connection_string": "postgresql://primary"}
    )

    # This provider cannot be resolved by type
    # Must use: container.resolve_provider(MyGroup.secondary_db_config)
    secondary_db_config = providers.Factory(
        DatabaseConfig,
        scope=Scope.APP,
        bound_type=None,  # <-- Step 1: Makes it unresolvable by type
        kwargs={"connection_string": "postgresql://secondary"}
    )

    # Step 2: Explicitly pass dependencies via kwargs for second repository or for both
    primary_repository = providers.Factory(
        Repository,  # <-- Implicit dependency, no kwargs
        scope=Scope.APP,
    )

    secondary_repository = providers.Factory(
        Repository,
        scope=Scope.APP,
        kwargs={"db_config": secondary_db_config}  # <-- Step 2: Explicit dependency
    )
```

## See also

- [Factories](../providers/factories.md#bound_type), the `bound_type` section.
- [Errors and exceptions](../providers/errors-and-exceptions.md)
- [Missing provider](../troubleshooting/missing-provider.md)

For binding an abstract type to a concrete implementation, `Alias` is preferred over duplicate factories.
