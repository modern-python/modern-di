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
instance = container.resolve_provider(Dependencies.independent_factory)
assert isinstance(instance, IndependentFactory)
```

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
