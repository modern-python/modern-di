from modern_di import AsyncContainer, Scope, providers


container_provider = providers.ContainerProvider(Scope.APP)


async def test_container_provider() -> None:
    async with AsyncContainer() as app_container:
        instance1 = await app_container.resolve_provider(container_provider)
        instance2 = await app_container.resolve_provider(container_provider)
        assert instance1 is instance2 is app_container
