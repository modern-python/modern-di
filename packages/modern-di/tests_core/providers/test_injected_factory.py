import dataclasses
import datetime

import pytest
from modern_di import Container, Scope, providers

from tests_core.creators import create_async_resource, create_sync_resource


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: datetime.datetime


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
request_sync_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=sync_resource.cast)
request_async_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=async_resource.cast)


async def test_injected_async_factory() -> None:
    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        factory = await request_async_factory.factory_provider.async_resolve(request_container)
        instance1, instance2 = factory(), factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)


async def test_injected_sync_factory() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        factory = request_sync_factory.factory_provider.sync_resolve(request_container)
        instance1, instance2 = factory(), factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)


async def test_injected_async_factory_in_sync_mode() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        with pytest.raises(RuntimeError, match="Resolving async resource in sync container is not allowed"):
            await request_async_factory.factory_provider.async_resolve(request_container)

        with pytest.raises(RuntimeError, match="Async resource cannot be resolved synchronously"):
            request_async_factory.factory_provider.sync_resolve(request_container)
