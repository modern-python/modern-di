# Cast Attribute

The `.cast` attribute is a special attribute available on all provider instances that allows you to reference the provider's type annotation for use in other providers' dependencies.

## Purpose

When defining dependencies between providers, you need a way to reference one provider as a dependency of another. The `.cast` attribute provides this reference while maintaining type safety.

## Usage

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    # Define a provider
    database_url = providers.Object(Scope.APP, "postgresql://localhost/mydb")
    
    # Use .cast to reference it as a dependency in another provider
    database_connection = providers.Factory(
        Scope.APP, 
        create_database_connection, 
        url=database_url.cast  # Reference the provider using .cast
    )
```

## Type Safety

The `.cast` attribute preserves the type information of the provider, ensuring that type checkers like mypy can properly validate your dependency graph:

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    # This provider has type str
    config_value = providers.Object(Scope.APP, "some_value")
    
    # When using .cast, the type is preserved
    # A function expecting a str parameter will be correctly type-checked
    processor = providers.Factory(
        Scope.APP,
        process_config_value,  # This function expects a str parameter
        value=config_value.cast
    )
```

## When to Use

Use `.cast` whenever you need to pass one provider as a dependency to another provider. This applies to all provider types:

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    # Resource provider
    db_engine = providers.Resource(Scope.APP, create_db_engine)
    
    # Factory provider that depends on the resource
    user_repository = providers.Factory(
        Scope.REQUEST,
        UserRepository,
        engine=db_engine.cast  # Use .cast to reference the resource
    )
    
    # Singleton provider that depends on the factory
    user_service = providers.Singleton(
        Scope.APP,
        UserService,
        repository=user_repository.cast  # Use .cast to reference the factory
    )
```

## Important Notes

1. The `.cast` attribute is only used for defining dependencies between providers
2. When resolving providers, you use the container's resolution methods, not `.cast`:

```python
# Correct way to resolve a provider
with AsyncContainer(groups=[Dependencies], scope=Scope.APP) as container:
    # Use container methods to resolve, not .cast
    db_engine_instance = container.sync_resolve_provider(Dependencies.db_engine)
    
# Incorrect - .cast is not used for resolution
# db_engine_instance = Dependencies.db_engine.cast  # This won't work
```

3. The `.cast` attribute maintains full type information for static analysis tools
