import datetime

from modern_di import AsyncContainer, Scope, providers


context_provider = providers.ContextProvider(Scope.APP, datetime.datetime)
request_context_provider = providers.ContextProvider(Scope.REQUEST, datetime.datetime)


async def test_context_provider() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with AsyncContainer(context={datetime.datetime: now}) as app_container:
        instance1 = await app_container.resolve_provider(context_provider)
        instance2 = await app_container.resolve_provider(context_provider)
        assert instance1 is instance2 is now


async def test_context_provider_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    async with (
        AsyncContainer() as app_container,
        app_container.build_child_container(context={datetime.datetime: now}, scope=Scope.REQUEST) as request_container,
    ):
        instance1 = await request_container.resolve_provider(request_context_provider)
        instance2 = await request_container.resolve_provider(request_context_provider)
        assert instance1 is instance2 is now
