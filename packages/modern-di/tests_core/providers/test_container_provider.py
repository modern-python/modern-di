from modern_di import Container, Scope, providers


container_provider = providers.ContainerProvider(Scope.APP)


async def test_container_provider() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await container_provider.async_resolve(app_container)
        instance2 = container_provider.sync_resolve(app_container)
        assert instance1 is instance2 is app_container
