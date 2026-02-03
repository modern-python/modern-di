# Factories

Factories are providers that create instances of dependencies.

## Parameters

When creating a Factory provider, you can configure several parameters:

### scope

Defines the lifecycle of the dependency. Available scopes are:
- `Scope.APP` - Tied to the entire application lifetime (default)
- `Scope.SESSION` - For websocket session lifetime
- `Scope.REQUEST` - For dependencies created for each user request
- `Scope.ACTION` - For lifetime less than request
- `Scope.STEP` - For lifetime less than ACTION

Providers can have dependencies only of the same or more long-lived scopes.

### creator

The callable (function or class) that will be invoked to create instances of the dependency.
Modern-DI analyzes the creator's signature to:
1. Determine the return type (used for `bound_type` if not explicitly set)
2. Identify parameter names and types for automatic dependency resolution

### bound_type

Explicitly sets the type for resolving by type. By default, this is automatically inferred from the creator's return type annotation.
Set to `None` to make the provider unresolvable by type.

### kwargs

Manual values for creator parameters that override automatic dependency resolution.
Use this to provide specific values for parameters or override automatically resolved dependencies.

### cache_settings

Configuration for caching instances. Only applicable for cached factories.
Use `providers.CacheSettings()` to enable caching with optional cleanup configuration.

### skip_creator_parsing

Disables automatic dependency resolution. When `True`:
- No automatic dependency resolution occurs
- All parameters must be provided via the `kwargs` parameter
- The `bound_type` will not be automatically inferred and defaults to `None`

## Types of factories 
There are two types of factories:

1. **Regular Factories** - Create a new instance on every call
2. **Cached Factories** - Create an instance once and cache it for future calls

### Regular Factories

Regular factories are initialized on every call.

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

### Cached Factories

Cached factories resolve the dependency only once and cache the resolved instance for future injections.

The caching mechanism is thread-safe, ensuring that even when multiple threads attempt to resolve the same cached factory simultaneously, only one instance will be created.

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

#### Cache Settings

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
