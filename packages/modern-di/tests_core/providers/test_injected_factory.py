import dataclasses
import datetime
import typing

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
        factory = await request_async_factory.async_provider.async_resolve(request_container)
        instance1, instance2 = await factory(), await factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)


async def test_injected_sync_factory() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        factory = request_sync_factory.sync_provider.sync_resolve(request_container)
        instance1, instance2 = factory(), factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)


async def test_injected_sync_factory_inside_factory() -> None:
    def factory_with_injected_factory(factory: typing.Callable[[], DependentCreator]) -> None:
        instance1 = factory()
        instance2 = factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)

    factory_with_injected_factory_dep = providers.Factory(
        Scope.REQUEST, factory_with_injected_factory, factory=request_sync_factory.sync_provider.cast
    )

    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        await factory_with_injected_factory_dep.async_resolve(request_container)


async def test_injected_async_factory_inside_resource() -> None:
    async def resource_with_injected_factory(
        factory: typing.Callable[[], typing.Awaitable[DependentCreator]],
    ) -> typing.AsyncIterator[None]:
        instance1 = await factory()
        instance2 = await factory()
        assert instance1 is not instance2
        assert isinstance(instance1, DependentCreator)
        assert isinstance(instance2, DependentCreator)
        yield

    resource_with_injected_factory_dep = providers.Resource(
        Scope.REQUEST, resource_with_injected_factory, factory=request_sync_factory.async_provider.cast
    )

    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        await resource_with_injected_factory_dep.async_resolve(request_container)


async def test_injected_async_factory_in_sync_mode() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        factory1 = await request_async_factory.sync_provider.async_resolve(request_container)
        with pytest.raises(RuntimeError, match="Resolving async resource in sync container is not allowed"):
            factory1()

        factory2 = request_async_factory.sync_provider.sync_resolve(request_container)
        with pytest.raises(RuntimeError, match="Resolving async resource in sync container is not allowed"):
            factory2()
