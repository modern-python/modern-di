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
        async_resource1 = await app_container.async_resolve_provider(async_resource)
        async_resource2 = await app_container.async_resolve_provider(async_resource)
        assert async_resource1 is async_resource2

    async with Container(scope=Scope.APP) as app_container:
        async_resource3 = await app_container.async_resolve_provider(async_resource)
        async_resource4 = await app_container.async_resolve_provider(async_resource)
        assert async_resource3 is async_resource4
        assert async_resource3 is not async_resource1


async def test_async_resource_from_class() -> None:
    async with Container(scope=Scope.APP) as app_container:
        async_resource1 = await app_container.async_resolve_provider(async_resource_from_class)
        async_resource2 = await app_container.async_resolve_provider(async_resource_from_class)
        assert async_resource1 is async_resource2

    async with Container(scope=Scope.APP) as app_container:
        async_resource3 = await app_container.async_resolve_provider(async_resource_from_class)
        async_resource4 = await app_container.async_resolve_provider(async_resource_from_class)
        assert async_resource3 is async_resource4
        assert async_resource3 is not async_resource1


async def test_async_resource_in_sync_container() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        pytest.raises(RuntimeError, match="Async resolving is forbidden in sync container"),
    ):
        await app_container.async_resolve_provider(async_resource)


async def test_async_resource_calling_sync_exit() -> None:
    async with Container(scope=Scope.APP) as app_container:
        await app_container.async_resolve_provider(async_resource)
        with pytest.raises(RuntimeError, match="Cannot tear down async context in `sync_tear_down`"):
            app_container.__exit__(None, None, None)


async def test_sync_resource() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await app_container.async_resolve_provider(sync_resource)
        sync_resource2 = await app_container.async_resolve_provider(sync_resource)
        assert sync_resource1 is sync_resource2

    with Container(scope=Scope.APP) as app_container:
        sync_resource3 = app_container.sync_resolve_provider(sync_resource)
        sync_resource4 = app_container.sync_resolve_provider(sync_resource)
        assert sync_resource3 is sync_resource4
        assert sync_resource3 is not sync_resource1


async def test_sync_resource_from_class() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await app_container.async_resolve_provider(sync_resource_from_class)
        sync_resource2 = await app_container.async_resolve_provider(sync_resource_from_class)
        assert sync_resource1 is sync_resource2

    with Container(scope=Scope.APP) as app_container:
        sync_resource3 = app_container.sync_resolve_provider(sync_resource_from_class)
        sync_resource4 = app_container.sync_resolve_provider(sync_resource_from_class)
        assert sync_resource3 is sync_resource4
        assert sync_resource3 is not sync_resource1


async def test_async_resource_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        async_resource1 = await app_container.async_resolve_provider(async_resource)

        app_container.override(async_resource, "override")

        async_resource2 = await app_container.async_resolve_provider(async_resource)
        async_resource3 = await app_container.async_resolve_provider(async_resource)

        app_container.reset_override()

        async_resource4 = await app_container.async_resolve_provider(async_resource)

        assert async_resource2 is not async_resource1
        assert async_resource2 is async_resource3
        assert async_resource4 is async_resource1


async def test_sync_resource_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        sync_resource1 = await app_container.async_resolve_provider(sync_resource)

        app_container.override(sync_resource, "override")

        sync_resource2 = app_container.sync_resolve_provider(sync_resource)
        sync_resource3 = await app_container.async_resolve_provider(sync_resource)

        app_container.reset_override()

        sync_resource4 = app_container.sync_resolve_provider(sync_resource)

        assert sync_resource2 is not sync_resource1
        assert sync_resource2 is sync_resource3
        assert sync_resource4 is sync_resource1


async def test_resource_unsupported_creator() -> None:
    with pytest.raises(TypeError, match="Unsupported resource type"):
        providers.Resource(Scope.APP, None)  # type: ignore[arg-type]


async def test_async_resource_sync_resolve() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="Resource cannot be resolved synchronously"):
            app_container.sync_resolve_provider(async_resource)


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
        return await container.async_resolve_provider(resource)

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
        return container.sync_resolve_provider(resource)

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
