import datetime

from modern_di import AsyncContainer, Scope, providers


def context_adapter_function(*, now: datetime.datetime, **_: object) -> datetime.datetime:
    return now


context_adapter = providers.ContextAdapter(Scope.APP, context_adapter_function)
request_context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


async def test_context_adapter() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with AsyncContainer(context={"now": now}) as app_container:
        instance1 = await app_container.resolve_provider(context_adapter)
        instance2 = await app_container.resolve_provider(context_adapter)
        assert instance1 is instance2 is now


async def test_context_adapter_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with (
        AsyncContainer() as app_container,
        app_container.build_child_container(context={"now": now}, scope=Scope.REQUEST) as request_container,
    ):
        instance1 = await request_container.resolve_provider(request_context_adapter)
        instance2 = await request_container.resolve_provider(request_context_adapter)
        assert instance1 is instance2 is now
