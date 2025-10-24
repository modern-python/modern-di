from modern_di import AsyncContainer, Scope, SyncContainer, providers


container_provider = providers.ContainerProvider(Scope.APP)


async def test_container_provider_async() -> None:
    async with AsyncContainer() as app_container:
        instance1 = await app_container.resolve_provider(container_provider)
        instance2 = await app_container.resolve_provider(container_provider)
        assert instance1 is instance2 is app_container


def test_container_provider_sync() -> None:
    with SyncContainer() as app_container:
        instance1 = app_container.resolve_provider(container_provider)
        instance2 = app_container.resolve_provider(container_provider)
        assert instance1 is instance2 is app_container
