import pytest
from modern_di import AsyncContainer, Scope, SyncContainer, providers

from tests_core.creators import create_async_resource, create_sync_resource


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
sequence = providers.List(Scope.APP, async_resource, sync_resource)
sync_sequence = providers.List(Scope.APP, sync_resource)


async def test_list_async() -> None:
    async with AsyncContainer() as app_container:
        sequence1 = await app_container.resolve_provider(sequence)
        sequence2 = await app_container.resolve_provider(sequence)
        resource1 = await app_container.resolve_provider(async_resource)
        resource2 = await app_container.resolve_provider(sync_resource)
        assert sequence1 == sequence2 == [resource1, resource2]

        assert await app_container.resolve_provider(sync_sequence) == [resource2]


def test_list_sync() -> None:
    with SyncContainer() as app_container:
        sequence1 = app_container.resolve_provider(sync_sequence)
        sequence2 = app_container.resolve_provider(sync_sequence)
        assert sequence1 is not sequence2


async def test_list_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dependency is REQUEST and current scope is APP"):
        providers.List(Scope.APP, request_factory_)
