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
        instance1 = await app_factory.async_resolve(app_container)
        instance2 = await app_factory.async_resolve(app_container)
        assert instance1 is not instance2


async def test_app_async_factory_forbidden_in_sync() -> None:
    async with Container(scope=Scope.APP) as app_container:
        with pytest.raises(RuntimeError, match="AsyncFactory cannot be resolved synchronously"):
            app_factory.sync_resolve(app_container)


async def test_async_factory_overridden_app_scope() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_factory.async_resolve(app_container)

        mock = await async_creator()
        app_factory.override(mock, container=app_container)

        instance2 = await app_factory.async_resolve(app_container)
        instance3 = await app_factory.async_resolve(app_container)
        assert instance1 is not instance2
        assert instance2 is instance3

        app_factory.reset_override(app_container)

        instance4 = await app_factory.async_resolve(app_container)

        assert instance4 is not instance3
