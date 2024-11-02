import pytest
from modern_di import Container, Scope, providers

from tests_core.creators import create_async_resource, create_sync_resource


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
sequence = providers.List(Scope.APP, async_resource, sync_resource)


async def test_list() -> None:
    async with Container(scope=Scope.APP, context={"option": "app"}) as app_container:
        sequence1 = await sequence.async_resolve(app_container)
        sequence2 = sequence.sync_resolve(app_container)
        resource1 = await async_resource.async_resolve(app_container)
        resource2 = sync_resource.sync_resolve(app_container)
        assert sequence1 == sequence2 == [resource1, resource2]


async def test_list_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dependency cannot be more than scope of dependent"):
        providers.List(Scope.APP, request_factory_)
