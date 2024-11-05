import pytest
from modern_di import Container, Scope, providers

from tests_core.creators import create_async_resource, create_sync_resource


async_resource = providers.Resource(Scope.APP, create_async_resource)
sync_resource = providers.Resource(Scope.APP, create_sync_resource)
mapping = providers.Dict(Scope.APP, dep1=async_resource, dep2=sync_resource)


async def test_dict() -> None:
    async with Container(scope=Scope.APP, context={"option": "app"}) as app_container:
        mapping1 = await mapping.async_resolve(app_container)
        mapping2 = mapping.sync_resolve(app_container)
        resource1 = await async_resource.async_resolve(app_container)
        resource2 = sync_resource.sync_resolve(app_container)
        assert mapping1 == mapping2 == {"dep1": resource1, "dep2": resource2}


async def test_dict_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dependency cannot be more than scope of dependent"):
        providers.Dict(Scope.APP, dep1=request_factory_)
