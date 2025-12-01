# Factories
Factories are initialized on every call.

## Factory
- A class or simple function is allowed.

```python
import dataclasses

from modern_di import Group, AsyncContainer, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class IndependentFactory:
    dep1: str
    dep2: int


class Dependencies(Group):
    independent_factory = providers.Factory(Scope.APP, IndependentFactory, dep1="text", dep2=123)


with AsyncContainer(groups=[Dependencies], scope=Scope.APP) as container:
    instance = container.sync_resolve_provider(Dependencies.independent_factory)
    assert isinstance(instance, IndependentFactory)
```

## AsyncFactory
- An async function is required.

```python
import datetime

from modern_di import Group, AsyncContainer, Scope, providers


async def async_factory() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Dependencies(Group):
    async_factory = providers.AsyncFactory(Scope.APP, async_factory)


async with AsyncContainer(groups=[Dependencies], scope=Scope.APP) as container:
    instance = await container.resolve_provider(Dependencies.async_factory)
    assert isinstance(instance, datetime.datetime)
```
