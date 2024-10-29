import asyncio
import dataclasses
import typing

import pytest

from modern_di import Container, Scope, resolvers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


app_singleton = resolvers.Singleton(Scope.APP, SimpleCreator, dep1="original")
request_singleton = resolvers.Singleton(Scope.REQUEST, DependentCreator, dep1=app_singleton.cast)


async def test_app_singleton() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = await app_singleton.async_resolve(app_container)
        singleton2 = await app_singleton.async_resolve(app_container)
        assert singleton1 is singleton2

    with Container(scope=Scope.APP) as app_container:
        singleton3 = app_singleton.sync_resolve(app_container)
        singleton4 = app_singleton.sync_resolve(app_container)
        assert singleton3 is singleton4
        assert singleton3 is not singleton1

    async with Container(scope=Scope.APP) as app_container:
        singleton5 = await app_singleton.async_resolve(app_container)
        singleton6 = await app_singleton.async_resolve(app_container)
        assert singleton5 is singleton6
        assert singleton5 is not singleton3
        assert singleton5 is not singleton1


async def test_request_singleton() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container() as request_container:
            instance1 = request_singleton.sync_resolve(request_container)
            instance2 = request_singleton.sync_resolve(request_container)
            assert instance1 is instance2

        async with app_container.build_child_container() as request_container:
            instance3 = await request_singleton.async_resolve(request_container)
            instance4 = await request_singleton.async_resolve(request_container)
            assert instance3 is instance4

        assert instance1 is not instance3


async def test_app_singleton_in_request_scope() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container():
            singleton1 = await app_singleton.async_resolve(app_container)

        async with app_container.build_child_container():
            singleton2 = await app_singleton.async_resolve(app_container)

        assert singleton1 is singleton2


async def test_singleton_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = app_singleton.sync_resolve(app_container)

        app_singleton.override(SimpleCreator(dep1="override"), container=app_container)

        singleton2 = app_singleton.sync_resolve(app_container)
        singleton3 = await app_singleton.async_resolve(app_container)

        app_singleton.reset_override(app_container)

        singleton4 = app_singleton.sync_resolve(app_container)

        assert singleton2 is not singleton1
        assert singleton2 is singleton3
        assert singleton4 is singleton1


async def test_singleton_race_condition() -> None:
    calls: int = 0

    async def create_resource() -> typing.AsyncIterator[str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ""

    resource = resolvers.Resource(Scope.APP, create_resource)
    factory_with_resource = resolvers.Singleton(Scope.APP, SimpleCreator, dep1=resource.cast)

    async def resolve_factory(container: Container) -> SimpleCreator:
        return await factory_with_resource.async_resolve(container)

    async with Container(scope=Scope.APP) as app_container:
        client1, client2 = await asyncio.gather(resolve_factory(app_container), resolve_factory(app_container))

    assert client1 is client2
    assert calls == 1


async def test_singleton_wrong_dependency_scope() -> None:
    def some_factory(_: SimpleCreator) -> None: ...

    request_singleton_ = resolvers.Singleton(Scope.REQUEST, SimpleCreator, dep1="original")
    with pytest.raises(RuntimeError, match="Scope of dependency cannot be more than scope of dependent"):
        resolvers.Singleton(Scope.APP, some_factory, request_singleton_.cast)
