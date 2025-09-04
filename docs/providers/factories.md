# Factories
Factories are initialized on every call.

## Factory
- Class or simple function is allowed.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class IndependentFactory:
    dep1: str
    dep2: int


class Dependencies(Group):
    independent_factory = providers.Factory(Scope.APP, IndependentFactory, dep1="text", dep2=123)


with Container(scope=Scope.APP) as container:
    instance = Dependencies.independent_factory.sync_resolve(container)
    assert isinstance(instance, IndependentFactory)
```

## AsyncFactory
- Async function is required.

```python
import datetime

from modern_di import Group, Container, Scope, providers


async def async_factory() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Dependencies(Group):
    async_factory = providers.AsyncFactory(Scope.APP, async_factory)


async with Container(scope=Scope.APP) as container:
    instance = await Dependencies.async_factory.async_resolve(container)
    assert isinstance(instance, datetime.datetime)
```
