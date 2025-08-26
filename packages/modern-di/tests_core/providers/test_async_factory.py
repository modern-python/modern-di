import asyncio
import datetime

import pytest
from modern_di import Container, Scope, providers


async def async_creator() -> datetime.datetime:
    await asyncio.sleep(0)
    return datetime.datetime.now(tz=datetime.timezone.utc)


app_factory = providers.AsyncFactory(Scope.APP, async_creator)


async def test_app_async_factory() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_container.async_resolve_provider(app_factory)
        instance2 = await app_container.async_resolve_provider(app_factory)
        assert instance1 is not instance2


async def test_app_async_factory_forbidden_in_sync() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="AsyncFactory cannot be resolved synchronously"):
            app_container.sync_resolve_provider(app_factory)


async def test_async_factory_overridden_app_scope() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_container.async_resolve_provider(app_factory)

        mock = await async_creator()
        app_container.override(app_factory, mock)

        instance2 = await app_container.async_resolve_provider(app_factory)
        instance3 = await app_container.async_resolve_provider(app_factory)
        assert instance1 is not instance2
        assert instance2 is instance3

        app_container.reset_override(app_factory)

        instance4 = await app_container.async_resolve_provider(app_factory)

        assert instance4 is not instance3
