from modern_di import Container, Scope, providers


container_provider = providers.ContainerProvider(Scope.APP)


async def test_container_provider() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_container.async_resolve_provider(container_provider)
        instance2 = app_container.sync_resolve_provider(container_provider)
        assert instance1 is instance2 is app_container
