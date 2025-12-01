# Singleton and AsyncSingleton

- They resolve the dependency only once and cache the resolved instance for future injections;
- A class or simple function is allowed.

## How it works

```python
import asyncio
import datetime
import pytest
import random

from modern_di import Group, AsyncContainer, Scope, providers


def generate_random_number() -> float:
    return random.random()


async def async_creator() -> datetime.datetime:
    await asyncio.sleep(0)
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Dependencies(Group):
    singleton = providers.Singleton(Scope.APP, generate_random_number)
    async_singleton = providers.AsyncSingleton(Scope.APP, async_creator)


with AsyncContainer() as container:
    # Sync resolving
    singleton_instance1 = container.sync_resolve_provider(Dependencies.singleton)
    with pytest.raises(RuntimeError, match="AsyncSingleton cannot be resolved synchronously"):
        container.sync_resolve_provider(Dependencies.async_singleton)

    # Async resolving
    singleton_instance2 = await container.resolve_provider(Dependencies.singleton)
    async_singleton_instance = await container.resolve_provider(Dependencies.async_singleton)

    # If resolved in the same container, the instance will be the same
    assert singleton_instance1 is singleton_instance2
```

## Concurrency safety

`Singleton` is safe to use in threading and asyncio concurrency:

```python
async with AsyncContainer() as container:
    # Calling resolve_provider concurrently in different coroutines will create only one instance
    await container.resolve_provider(Dependencies.singleton)

    # Calling sync_resolve_provider concurrently in different threads will create only one instance
    container.sync_resolve_provider(Dependencies.singleton)
```
