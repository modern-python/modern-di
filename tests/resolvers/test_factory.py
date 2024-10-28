import asyncio
import dataclasses
import typing

import pytest

from modern_di import Container, Scope, resolvers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleFactory:
    dep1: str


singleton = resolvers.Factory(Scope.APP, SimpleFactory, dep1="original")


async def test_factory() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = await singleton.async_resolve(app_container)
        singleton2 = await singleton.async_resolve(app_container)
        assert singleton1 is singleton2

    with Container(scope=Scope.APP) as app_container:
        singleton3 = singleton.sync_resolve(app_container)
        singleton4 = singleton.sync_resolve(app_container)
        assert singleton3 is singleton4
        assert singleton3 is not singleton1

    async with Container(scope=Scope.APP) as app_container:
        singleton5 = await singleton.async_resolve(app_container)
        singleton6 = await singleton.async_resolve(app_container)
        assert singleton5 is singleton6
        assert singleton5 is not singleton3
        assert singleton5 is not singleton1


async def test_factory_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = singleton.sync_resolve(app_container)

        singleton.override(SimpleFactory(dep1="override"), container=app_container)

        singleton2 = singleton.sync_resolve(app_container)
        singleton3 = await singleton.async_resolve(app_container)

        singleton.reset_override(app_container)

        singleton4 = singleton.sync_resolve(app_container)

        assert singleton2 is not singleton1
        assert singleton2 is singleton3
        assert singleton4 is singleton1


async def test_factory_race_condition() -> None:
    calls: int = 0

    async def create_resource() -> typing.AsyncIterator[str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ""

    resource = resolvers.Resource(Scope.APP, create_resource)
    factory_with_resource = resolvers.Factory(Scope.APP, SimpleFactory, dep1=resource.cast)

    async def resolve_factory(container: Container) -> SimpleFactory:
        return await factory_with_resource.async_resolve(container)

    async with Container(scope=Scope.APP) as app_container:
        client1, client2 = await asyncio.gather(resolve_factory(app_container), resolve_factory(app_container))

    assert client1 == client2
    assert calls == 1


async def test_factory_wrong_dependency_scope() -> None:
    def some_factory(_: SimpleFactory) -> None: ...

    request_factory = resolvers.Factory(Scope.REQUEST, SimpleFactory, dep1="original")
    with pytest.raises(RuntimeError, match="Scope of dependency cannot be more than scope of dependent"):
        resolvers.Factory(Scope.APP, some_factory, request_factory.cast)
