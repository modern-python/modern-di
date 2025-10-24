import pytest
from modern_di import AsyncContainer, Scope, SyncContainer, providers

from tests_core.creators import create_async_resource, create_sync_resource


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
mapping = providers.Dict(Scope.APP, dep1=async_resource, dep2=sync_resource)
sync_mapping = providers.Dict(Scope.APP, dep2=sync_resource)


async def test_dict_async() -> None:
    async with AsyncContainer() as app_container:
        mapping1 = await app_container.resolve_provider(mapping)
        mapping2 = await app_container.resolve_provider(mapping)
        resource1 = await app_container.resolve_provider(async_resource)
        resource2 = await app_container.resolve_provider(sync_resource)
        assert mapping1 == mapping2 == {"dep1": resource1, "dep2": resource2}

        assert await app_container.resolve_provider(sync_mapping) == {"dep2": resource2}


def test_dict_sync() -> None:
    with SyncContainer() as app_container:
        mapping1 = app_container.resolve_provider(sync_mapping)
        mapping2 = app_container.resolve_provider(sync_mapping)
        assert mapping1 is not mapping2


async def test_dict_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dep1 is REQUEST and current scope is APP"):
        providers.Dict(Scope.APP, dep1=request_factory_)
