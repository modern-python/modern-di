# Singleton and AsyncSingleton

- They resolve the dependency only once and cache the resolved instance for future injections;
- A class or simple function is allowed.

## How it works

```python
import asyncio
import datetime
import pytest
import random

from modern_di import Group, Container, Scope, providers


def generate_random_number() -> float:
    return random.random()


async def async_creator() -> datetime.datetime:
    await asyncio.sleep(0)
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Dependencies(Group):
    singleton = providers.Singleton(Scope.APP, generate_random_number)


container = Container()
singleton_instance1 = container.resolve_provider(Dependencies.singleton)
singleton_instance2 = container.resolve_provider(Dependencies.singleton)

# If resolved in the same container, the instance will be the same
assert singleton_instance1 is singleton_instance2
```

## Concurrency safety

`Singleton` is safe to use in threading and asyncio concurrency:

```python
container = Container()

# Calling resolve_provider concurrently in different threads will create only one instance
container.resolve_provider(Dependencies.singleton)
```
