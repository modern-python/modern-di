import asyncio
import threading
import time
import typing
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from modern_di import Container, Scope, providers

from tests_core.creators import (
    AsyncContextManagerResource,
    ContextManagerResource,
    create_async_resource,
    create_sync_resource,
)


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
async_resource_from_class = providers.Resource(Scope.APP, AsyncContextManagerResource)
sync_resource_from_class = providers.Resource(Scope.APP, ContextManagerResource)


async def test_async_resource() -> None:
    async with Container(scope=Scope.APP) as app_container:
        async_resource1 = await async_resource.async_resolve(app_container)
        async_resource2 = await async_resource.async_resolve(app_container)
        assert async_resource1 is async_resource2

    async with Container(scope=Scope.APP) as app_container:
        async_resource3 = await async_resource.async_resolve(app_container)
        async_resource4 = async_resource.sync_resolve(app_container)
        assert async_resource3 is async_resource4
        assert async_resource3 is not async_resource1


async def test_async_resource_from_class() -> None:
    async with Container(scope=Scope.APP) as app_container:
        async_resource1 = await async_resource_from_class.async_resolve(app_container)
        async_resource2 = await async_resource_from_class.async_resolve(app_container)
        assert async_resource1 is async_resource2

    async with Container(scope=Scope.APP) as app_container:
        async_resource3 = await async_resource_from_class.async_resolve(app_container)
        async_resource4 = async_resource_from_class.sync_resolve(app_container)
        assert async_resource3 is async_resource4
        assert async_resource3 is not async_resource1


async def test_async_resource_in_sync_container() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        pytest.raises(RuntimeError, match="Resolving async resource in sync container is not allowed"),
    ):
        await async_resource.async_resolve(app_container)


async def test_async_resource_calling_sync_exit() -> None:
    async with Container(scope=Scope.APP) as app_container:
        await async_resource.async_resolve(app_container)
        with pytest.raises(RuntimeError, match="Cannot tear down async context in `sync_tear_down`"):
            app_container.__exit__(None, None, None)


async def test_sync_resource() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await sync_resource.async_resolve(app_container)
        sync_resource2 = await sync_resource.async_resolve(app_container)
        assert sync_resource1 is sync_resource2

    with Container(scope=Scope.APP) as app_container:
        sync_resource3 = sync_resource.sync_resolve(app_container)
        sync_resource4 = sync_resource.sync_resolve(app_container)
        assert sync_resource3 is sync_resource4
        assert sync_resource3 is not sync_resource1


async def test_sync_resource_from_class() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await sync_resource_from_class.async_resolve(app_container)
        sync_resource2 = await sync_resource_from_class.async_resolve(app_container)
        assert sync_resource1 is sync_resource2

    with Container(scope=Scope.APP) as app_container:
        sync_resource3 = sync_resource_from_class.sync_resolve(app_container)
        sync_resource4 = sync_resource_from_class.sync_resolve(app_container)
        assert sync_resource3 is sync_resource4
        assert sync_resource3 is not sync_resource1


async def test_async_resource_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        async_resource1 = await async_resource.async_resolve(app_container)

        async_resource.override("override", container=app_container)

        async_resource2 = async_resource.sync_resolve(app_container)
        async_resource3 = await async_resource.async_resolve(app_container)

        app_container.reset_override()

        async_resource4 = async_resource.sync_resolve(app_container)

        assert async_resource2 is not async_resource1
        assert async_resource2 is async_resource3
        assert async_resource4 is async_resource1


async def test_sync_resource_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await sync_resource.async_resolve(app_container)

        sync_resource.override("override", container=app_container)

        sync_resource2 = sync_resource.sync_resolve(app_container)
        sync_resource3 = await sync_resource.async_resolve(app_container)

        app_container.reset_override()

        sync_resource4 = sync_resource.sync_resolve(app_container)

        assert sync_resource2 is not sync_resource1
        assert sync_resource2 is sync_resource3
        assert sync_resource4 is sync_resource1


async def test_resource_unsupported_creator() -> None:
    with pytest.raises(TypeError, match="Unsupported resource type"):
        providers.Resource(Scope.APP, None)  # type: ignore[arg-type]


async def test_async_resource_sync_resolve() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="Async resource cannot be resolved synchronously"):
            async_resource.sync_resolve(app_container)


@pytest.mark.repeat(10)
async def test_resource_asyncio_concurrency() -> None:
    calls: int = 0

    async def create_resource() -> typing.AsyncIterator[str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ""

    resource = providers.Resource(Scope.APP, create_resource)

    async def resolve_resource(container: Container) -> str:
        return await resource.async_resolve(container)

    async with Container(scope=Scope.APP) as app_container:
        await asyncio.gather(resolve_resource(app_container), resolve_resource(app_container))

    assert calls == 1


@pytest.mark.repeat(10)
def test_resource_threading_concurrency() -> None:
    calls: int = 0
    lock = threading.Lock()

    def create_resource() -> typing.Iterator[str]:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.01)
        yield ""

    resource = providers.Resource(Scope.APP, create_resource)

    def resolve_resource(container: Container) -> str:
        return resource.sync_resolve(container)

    with Container(scope=Scope.APP) as app_container, ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(resolve_resource, app_container),
            pool.submit(resolve_resource, app_container),
            pool.submit(resolve_resource, app_container),
            pool.submit(resolve_resource, app_container),
        ]
        results = [x.result() for x in as_completed(tasks)]

    assert results == ["", "", "", ""]
    assert calls == 1
