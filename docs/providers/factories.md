# Factories

Factories are providers that create instances of dependencies. There are two types of factories:

1. **Regular Factories** - Create a new instance on every call
2. **Cached Factories** - Create an instance once and cache it for future calls

## Regular Factories

Regular factories are initialized on every call.

- A class or simple function is allowed.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
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
instance2 = container.resolve(dependency_type=IndependentFactory)
assert isinstance(instance2, IndependentFactory)

# Resolve by name (uses the attribute name in the Group)
instance3 = container.resolve(dependency_name="independent_factory")
assert isinstance(instance3, IndependentFactory)
```

### Resolving Dependencies

Dependencies can be resolved in three ways:

1. **By provider reference** - Using `container.resolve_provider(provider)`
2. **By type** - Using `container.resolve(dependency_type=SomeType)`
3. **By name** - Using `container.resolve(dependency_name="provider_name")`

When resolving by type, the container looks for a provider whose `bound_type` matches the requested type.
By default, the `bound_type` is automatically inferred from the creator's return type annotation.

When resolving by name, the container looks for a provider with a matching attribute name in the Group.

## Cached Factories

Cached factories resolve the dependency only once and cache the resolved instance for future injections.

### Thread Safety

The caching mechanism is thread-safe, ensuring that even when multiple threads attempt to resolve the same cached factory simultaneously, only one instance will be created.

### How it works

```python
import random

from modern_di import Group, Container, Scope, providers


def generate_random_number() -> float:
    return random.random()


class Dependencies(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=generate_random_number,
        cache_settings=providers.CacheSettings()
    )


container = Container()
singleton_instance1 = container.resolve_provider(Dependencies.singleton)
singleton_instance2 = container.resolve_provider(Dependencies.singleton)

# If resolved in the same container, the instance will be the same
assert singleton_instance1 is singleton_instance2
```

### Cache Settings

You can customize caching behavior with `CacheSettings`:

```python
from modern_di import Group, Scope, providers

def create_resource() -> SomeResource:
    # Create and return resource
    pass

class Dependencies(Group):
    # Cache with cleanup
    resource = providers.Factory(
        scope=Scope.APP,
        creator=create_resource,
        cache_settings=providers.CacheSettings(
            finalizer=lambda res: res.close(),  # Cleanup function
            clear_cache=False  # Keep cache after close
        )
    )
```

## Creator Parsing and Manual Dependency Injection

By default, Modern-DI automatically parses the creator function or class to determine:
1. The return type (used for `bound_type`)
2. The parameter types (used for automatic dependency resolution)

However, there are cases where you might want to disable this automatic parsing:

### Skipping Creator Parsing

You can disable automatic creator parsing by setting `skip_creator_parsing=True`:

```python
from modern_di import Group, Container, Scope, providers

@dataclasses.dataclass
class MyService:
    config_value: str
    computed_value: int

class Dependencies(Group):
    # Skip parsing - you must provide all dependencies manually
    my_service = providers.Factory(
        scope=Scope.APP,
        creator=MyService,
        kwargs={"config_value": "example", "computed_value": 42},
        skip_creator_parsing=True
    )

container = Container(groups=[Dependencies])
service = container.resolve_provider(Dependencies.my_service)
```

When `skip_creator_parsing=True`:
- No automatic dependency resolution occurs
- All parameters must be provided via the `kwargs` parameter
- The `bound_type` will not be automatically inferred and defaults to `None`

### Manual Dependency Injection

Even when not skipping creator parsing, you can still override automatic dependency resolution by providing explicit values in `kwargs`:

```python
from modern_di import Group, Container, Scope, providers

@dataclasses.dataclass
class DatabaseConfig:
    host: str
    port: int

@dataclasses.dataclass
class DatabaseConnection:
    config: DatabaseConfig
    timeout: int = 30

class Dependencies(Group):
    db_config = providers.Factory(
        scope=Scope.APP,
        creator=DatabaseConfig,
        kwargs={"host": "localhost", "port": 5432}
    )

    # Override automatic dependency resolution for timeout
    db_connection = providers.Factory(
        scope=Scope.APP,
        creator=DatabaseConnection,
        kwargs={"timeout": 60}  # Override the default timeout
    )

container = Container(groups=[Dependencies])
connection = container.resolve_provider(Dependencies.db_connection)
```

In this example, the `db_connection` provider will automatically resolve the `config` parameter from the `db_config` provider, but will use the manually provided value of `60` for the `timeout` parameter instead of the default `30`.
