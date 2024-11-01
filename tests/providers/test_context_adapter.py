import datetime

from modern_di import Container, Scope, providers


def context_adapter_function(*, now: datetime.datetime, **_: object) -> datetime.datetime:
    return now


context_adapter = providers.ContextAdapter(Scope.APP, context_adapter_function)
request_context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


async def test_context_adapter() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with Container(scope=Scope.APP, context={"now": now}) as app_container:
        instance1 = await context_adapter.async_resolve(app_container)
        instance2 = context_adapter.sync_resolve(app_container)
        assert instance1 is instance2 is now


async def test_context_adapter_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(context={"now": now}) as request_container,
    ):
        instance1 = await request_context_adapter.async_resolve(request_container)
        instance2 = request_context_adapter.sync_resolve(request_container)
        assert instance1 is instance2 is now
