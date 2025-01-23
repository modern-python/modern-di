# Singleton

- resolve the dependency only once and cache the resolved instance for future injections;
- class or simple function is allowed.

## How it works

```python
import random

from modern_di import BaseGraph, Container, Scope, providers


def generate_random_number() -> float:
    return random.random()


class Dependencies(BaseGraph):
    singleton = providers.Singleton(Scope.APP, generate_random_number)


with Container(scope=Scope.APP) as container:
    # sync resolving
    singleton_instance1 = Dependencies.singleton.sync_resolve(container)
    
    # async resolving
    singleton_instance2 = await Dependencies.singleton.async_resolve(container)

    # if resolved in the same container, the instance will be the same
    assert singleton_instance1 is singleton_instance2
```

## Concurrency safety

`Singleton` is safe to use in threading and asyncio concurrency:

```python
with Container(scope=Scope.APP) as container:
    # calling async_resolve concurrently in different coroutines will create only one instance
    await Dependencies.singleton.async_resolve(container)
    
    # calling sync_resolve concurrently in different threads will create only one instance
    Dependencies.singleton.sync_resolve(container)
```
