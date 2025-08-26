import asyncio
import datetime
import uuid

import pytest
from modern_di import Container, Scope, providers


async def async_creator() -> datetime.datetime:
    await asyncio.sleep(0)
    return datetime.datetime.now(tz=datetime.timezone.utc)


async_singleton = providers.AsyncSingleton(Scope.APP, async_creator)


async def test_app_async_singleton() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_container.async_resolve_provider(async_singleton)
        instance2 = await app_container.async_resolve_provider(async_singleton)
        assert instance1 is instance2


async def test_app_async_singleton_forbidden_in_sync() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="AsyncSingleton cannot be resolved synchronously"):
            app_container.sync_resolve_provider(async_singleton)


async def test_async_singleton_overridden_app_scope() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_container.async_resolve_provider(async_singleton)

        mock = await async_creator()
        app_container.override(async_singleton, mock)

        instance2 = await app_container.async_resolve_provider(async_singleton)
        instance3 = await app_container.async_resolve_provider(async_singleton)
        assert instance1 is not instance2
        assert instance2 is instance3

        app_container.reset_override(async_singleton)

        instance4 = await app_container.async_resolve_provider(async_singleton)

        assert instance4 is not instance3
        assert instance4 is instance1


@pytest.mark.repeat(10)
async def test_async_singleton_asyncio_concurrency() -> None:
    calls: int = 0

    async def create_singleton() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return str(uuid.uuid4())

    async_singleton_ = providers.AsyncSingleton(Scope.APP, create_singleton)

    async def resolve_factory(container: Container) -> str:
        return await container.async_resolve_provider(async_singleton_)

    async with Container(scope=Scope.APP) as app_container:
        instance1, instance2 = await asyncio.gather(resolve_factory(app_container), resolve_factory(app_container))

    assert instance1 is instance2
    assert calls == 1
