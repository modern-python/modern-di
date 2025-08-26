import datetime

from modern_di import Container, Scope, providers


def context_adapter_function(*, now: datetime.datetime, **_: object) -> datetime.datetime:
    return now


context_adapter = providers.ContextAdapter(Scope.APP, context_adapter_function)
request_context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


async def test_context_adapter() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with Container(scope=Scope.APP, context={"now": now}) as app_container:
        instance1 = await app_container.async_resolve_provider(context_adapter)
        instance2 = app_container.sync_resolve_provider(context_adapter)
        assert instance1 is instance2 is now


async def test_context_adapter_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(context={"now": now}, scope=Scope.REQUEST) as request_container,
    ):
        instance1 = await request_container.async_resolve_provider(request_context_adapter)
        instance2 = request_container.sync_resolve_provider(request_context_adapter)
        assert instance1 is instance2 is now
