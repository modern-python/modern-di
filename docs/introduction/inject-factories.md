# Injecting factories

When you need to inject the factory itself, but not the result of its call, use:

1. `.async_provider` attribute for async resolver
2. `.sync_provider` attribute for sync resolver

Let's first define providers with container:
```python
import dataclasses
import datetime
import typing

from modern_di import BaseGraph, Container, Scope, providers


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    yield datetime.datetime.now(tz=datetime.timezone.utc)


@dataclasses.dataclass(kw_only=True, slots=True)
class SomeFactory:
    start_at: datetime.datetime


@dataclasses.dataclass(kw_only=True, slots=True)
class FactoryWithFactories:
    sync_factory: typing.Callable[..., SomeFactory]
    async_factory: typing.Callable[..., typing.Coroutine[typing.Any, typing.Any, SomeFactory]]


class DIContainer(BaseGraph):
    async_resource = providers.Resource(Scope.APP, create_async_resource)
    dependent_factory = providers.Factory(Scope.APP, SomeFactory, start_at=async_resource.cast)
    factory_with_factories = providers.Factory(
        Scope.APP,
        FactoryWithFactories,
        sync_factory=dependent_factory.sync_provider.cast,
        async_factory=dependent_factory.async_provider.cast,
    )
```

Async factory from `.async_provider` attribute can be used like this:
```python
async with Container(scope=Scope.APP) as app_container:
    factory_with_factories = await DIContainer.factory_with_factories.async_resolve(app_container)
    instance1 = await factory_with_factories.async_factory()
    instance2 = await factory_with_factories.async_factory()
    assert instance1 is not instance2
```

Sync factory from `.sync_provider` attribute can be used like this:
```python
async with Container(scope=Scope.APP) as app_container:
    await DIContainer.async_resolve_creators(app_container)
    factory_with_factories = await DIContainer.factory_with_factories.sync_resolve(app_container)
    instance1 = factory_with_factories.sync_factory()
    instance2 = factory_with_factories.sync_factory()
    assert instance1 is not instance2
```
