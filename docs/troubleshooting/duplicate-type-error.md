# Duplicate Type Error

This error occurs when two or more providers are registered with the same `bound_type`. Modern-DI uses the `bound_type` to resolve dependencies by type, so each type must be unique in the providers registry.

## Understanding the Error

When you see this error:

```
DuplicateProviderTypeError: Provider is duplicated by type <class 'SomeType'>.
```

The full runtime message also embeds the numbered resolution steps (set `bound_type=None` on one of the providers, or pass dependencies via `kwargs`) and a `See https://...` backlink to this page.

It descends from `RegistrationError` → `ModernDIError` → `RuntimeError`, so `except DuplicateProviderTypeError`, `except RegistrationError`, and `except RuntimeError` all catch it. See [Errors and exceptions](../providers/errors-and-exceptions.md).

This typically happens when:

1. You have multiple factories that return the same type
2. You're using the same class in different contexts with different configurations

## How to Resolve

To fix this error, you need to:

1. Set `bound_type=None` on one of the duplicate providers to make it unresolvable by type
2. Explicitly pass dependencies via the `kwargs` parameter to avoid automatic resolution

Here's a complete example showing both steps:

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
        scope=Scope.APP,
        creator=DatabaseConfig,
        kwargs={"connection_string": "postgresql://primary"}
    )

    # This provider cannot be resolved by type
    # Must use: container.resolve_provider(MyGroup.secondary_db_config)
    secondary_db_config = providers.Factory(
        scope=Scope.APP,
        creator=DatabaseConfig,
        bound_type=None,  # <-- Step 1: Makes it unresolvable by type
        kwargs={"connection_string": "postgresql://secondary"}
    )

    # Step 2: Explicitly pass dependencies via kwargs for second repository or for both
    primary_repository = providers.Factory(
        scope=Scope.APP,
        creator=Repository,  # <-- Implicit dependency, no kwargs
    )

    secondary_repository = providers.Factory(
        scope=Scope.APP,
        creator=Repository,
        kwargs={"db_config": secondary_db_config}  # <-- Step 2: Explicit dependency
    )
```

## See also

- [Factories](../providers/factories.md#bound_type) — the `bound_type` section.
- [Errors and exceptions](../providers/errors-and-exceptions.md)
- [Missing provider](../troubleshooting/missing-provider.md)

For binding an abstract type to a concrete implementation, `Alias` is preferred over duplicate factories.
