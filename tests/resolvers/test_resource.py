import asyncio
import datetime
import logging
import typing

import pytest

from modern_di import Container, Scope, resolvers


logger = logging.getLogger(__name__)


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    logger.debug("Async resource initiated")
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        logger.debug("Async resource destructed")


def create_sync_resource() -> typing.Iterator[datetime.datetime]:
    logger.debug("Resource initiated")
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        logger.debug("Resource destructed")


async_resource = resolvers.Resource(Scope.APP, create_async_resource)
sync_resource = resolvers.Resource(Scope.APP, create_sync_resource)


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


async def test_async_resource_race_condition() -> None:
    calls: int = 0

    async def create_resource() -> typing.AsyncIterator[str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ""

    resource = resolvers.Resource(Scope.APP, create_resource)

    async def resolve_resource(container: Container) -> str:
        return await resource.async_resolve(container)

    async with Container(scope=Scope.APP) as app_container:
        await asyncio.gather(resolve_resource(app_container), resolve_resource(app_container))

    assert calls == 1


async def test_resource_unsupported_creator() -> None:
    with pytest.raises(RuntimeError, match="Unsupported resource type"):
        resolvers.Resource(Scope.APP, None)  # type: ignore[arg-type]


async def test_async_resource_sync_resolve() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="Async resource cannot be resolved synchronously"):
            async_resource.sync_resolve(app_container)
