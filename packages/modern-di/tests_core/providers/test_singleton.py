import asyncio
import dataclasses
import threading
import time
import typing
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from modern_di import Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


app_singleton = providers.Singleton(Scope.APP, SimpleCreator, dep1="original")
request_singleton = providers.Singleton(Scope.REQUEST, DependentCreator, dep1=app_singleton.cast)


async def test_app_singleton() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = await app_container.async_resolve_provider(app_singleton)
        singleton2 = await app_container.async_resolve_provider(app_singleton)
        assert singleton1 is singleton2

    with Container(scope=Scope.APP) as app_container:
        singleton3 = app_container.sync_resolve_provider(app_singleton)
        singleton4 = app_container.sync_resolve_provider(app_singleton)
        assert singleton3 is singleton4
        assert singleton3 is not singleton1

    async with Container(scope=Scope.APP) as app_container:
        singleton5 = await app_container.async_resolve_provider(app_singleton)
        singleton6 = await app_container.async_resolve_provider(app_singleton)
        assert singleton5 is singleton6
        assert singleton5 is not singleton3
        assert singleton5 is not singleton1


async def test_request_singleton() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
            instance1 = request_container.sync_resolve_provider(request_singleton)
            instance2 = request_container.sync_resolve_provider(request_singleton)
            assert instance1 is instance2

        async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
            instance3 = await request_container.async_resolve_provider(request_singleton)
            instance4 = await request_container.async_resolve_provider(request_singleton)
            assert instance3 is instance4

        assert instance1 is not instance3


async def test_app_singleton_in_request_scope() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container():
            singleton1 = await app_container.async_resolve_provider(app_singleton)

        async with app_container.build_child_container():
            singleton2 = await app_container.async_resolve_provider(app_singleton)

        assert singleton1 is singleton2


async def test_singleton_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = app_container.sync_resolve_provider(app_singleton)

        app_container.override(app_singleton, SimpleCreator(dep1="override"))

        singleton2 = app_container.sync_resolve_provider(app_singleton)
        singleton3 = await app_container.async_resolve_provider(app_singleton)

        app_container.reset_override(app_singleton)

        singleton4 = app_container.sync_resolve_provider(app_singleton)

        assert singleton2 is not singleton1
        assert singleton2 is singleton3
        assert singleton4 is singleton1


async def test_singleton_wrong_dependency_scope() -> None:
    def some_factory(_: SimpleCreator) -> None: ...

    request_singleton_ = providers.Singleton(Scope.REQUEST, SimpleCreator, dep1="original")
    with pytest.raises(RuntimeError, match="Scope of dependency is REQUEST and current scope is APP"):
        providers.Singleton(Scope.APP, some_factory, request_singleton_.cast)


@pytest.mark.repeat(10)
async def test_singleton_asyncio_concurrency() -> None:
    calls: int = 0

    async def create_resource() -> typing.AsyncIterator[str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ""

    resource = providers.Resource(Scope.APP, create_resource)
    factory_with_resource = providers.Singleton(Scope.APP, SimpleCreator, dep1=resource.cast)

    async def resolve_factory(container: Container) -> SimpleCreator:
        return await container.async_resolve_provider(factory_with_resource)

    async with Container(scope=Scope.APP) as app_container:
        client1, client2 = await asyncio.gather(resolve_factory(app_container), resolve_factory(app_container))

    assert client1 is client2
    assert calls == 1


@pytest.mark.repeat(10)
def test_singleton_threading_concurrency() -> None:
    calls: int = 0
    lock = threading.Lock()

    def create_singleton() -> str:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.01)
        return ""

    singleton = providers.Singleton(Scope.APP, create_singleton)

    def resolve_singleton(container: Container) -> str:
        return container.sync_resolve_provider(singleton)

    with Container(scope=Scope.APP) as app_container, ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
        ]
        results = [x.result() for x in as_completed(tasks)]

    assert all(x == "" for x in results)
    assert calls == 1


@pytest.mark.repeat(10)
def test_singleton_wth_resource_threading_concurrency() -> None:
    calls: int = 0
    lock = threading.Lock()

    def create_resource() -> typing.Iterator[str]:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.01)
        yield ""

    resource = providers.Resource(Scope.APP, create_resource)
    factory_with_resource = providers.Singleton(Scope.APP, SimpleCreator, dep1=resource.cast)

    def resolve_factory(container: Container) -> SimpleCreator:
        return container.sync_resolve_provider(factory_with_resource)

    with Container(scope=Scope.APP) as app_container, ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(resolve_factory, app_container),
            pool.submit(resolve_factory, app_container),
            pool.submit(resolve_factory, app_container),
            pool.submit(resolve_factory, app_container),
        ]
        results = [x.result() for x in as_completed(tasks)]

    assert all(isinstance(x, SimpleCreator) for x in results)
    assert calls == 1
